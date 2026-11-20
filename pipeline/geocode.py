"""3단계: 주소 -> 좌표(위도·경도) 변환.

마을숲 데이터에는 좌표가 없어서 주소로 위치를 찾는다. 주소 형식이 제각각이라 여러 방법을 차례로 시도한다.
  1) 주소 그대로 (시도 이름은 정식 명칭으로 바꿔서)
  2) 번지를 뺀 마을(리·동) 단위 주소
  3) 괄호 안 마을 이름 + 시군구 (키워드 검색, 카카오만)
  4) 숲 이름 + 시군구 (키워드 검색, 카카오만)

필요한 환경변수 (.env): KAKAO_REST_KEY 또는 VWORLD_KEY (둘 중 하나)
수작업 보정: data/geocode_overrides.csv (id,lat,lng,memo) 에 적으면 그 값이 우선한다.
결과: forests_clean.json 에 lat/lng 채움, data/work/geocode_check.csv (사람 확인용)
"""
import csv
import re
import time
from urllib.parse import quote

import requests

from common import ROOT, SIDO_LONG, SIDO_SHORT, WORK, env, load_json, save_json

CACHE = WORK / "geocode_cache.json"
OVERRIDES = ROOT / "data" / "geocode_overrides.csv"
KOREA = (33.0, 38.7, 124.5, 131.0)  # 위도, 경도 범위


def in_korea(lat, lng):
    return KOREA[0] <= lat <= KOREA[1] and KOREA[2] <= lng <= KOREA[3]


def kakao(kind, query, key):
    url = f"https://dapi.kakao.com/v2/local/search/{kind}.json"
    r = requests.get(url, params={"query": query, "size": 1}, headers={"Authorization": f"KakaoAK {key}"}, timeout=10)
    r.raise_for_status()
    docs = r.json().get("documents", [])
    if not docs:
        return None
    d = docs[0]
    return float(d["y"]), float(d["x"]), d.get("address_name") or d.get("place_name", "")


def vworld(query, key):
    for typ in ("PARCEL", "ROAD"):
        r = requests.get("https://api.vworld.kr/req/address", params={
            "service": "address", "request": "getcoord", "version": "2.0", "crs": "epsg:4326",
            "address": query, "refine": "true", "simple": "false", "format": "json", "type": typ, "key": key,
        }, timeout=10)
        r.raise_for_status()
        resp = r.json().get("response", {})
        if resp.get("status") == "OK":
            p = resp["result"]["point"]
            refined = resp.get("refined", {}).get("text", "")
            return float(p["y"]), float(p["x"]), refined
    return None


def queries(f):
    addr = f["address"]
    village = re.findall(r"\((.*?)\)", addr)
    base = re.sub(r"\(.*?\)", " ", addr)
    tokens = base.split()
    if tokens and f["sido"] and tokens[0] in SIDO_SHORT:
        tokens[0] = SIDO_LONG[f["sido"]]  # '전북', '전라북도' -> '전북특별자치도'
    full = " ".join(tokens)
    # 번지(숫자) 앞까지만 남기면 마을 단위 주소
    upto_ri = []
    for t in tokens:
        if re.match(r"^(산)?\d", t):
            break
        upto_ri.append(t)
    region = " ".join(x for x in [SIDO_LONG.get(f["sido"] or "", ""), f["sigungu"] or ""] if x)
    out = [("address", full)]
    if len(upto_ri) >= 3 and " ".join(upto_ri) != full:
        out.append(("address", " ".join(upto_ri)))
    for v in village:
        out.append(("keyword", f"{region} {v}".strip()))
    name = re.sub(r"\(.*?\)", "", f["name"])
    out.append(("keyword", f"{region} {name}".strip()))
    return out


def main():
    forests = load_json(WORK / "forests_clean.json")
    kakao_key, vworld_key = env("KAKAO_REST_KEY"), env("VWORLD_KEY")
    if not (kakao_key or vworld_key):
        raise SystemExit(".env 에 KAKAO_REST_KEY 또는 VWORLD_KEY 를 넣어주세요.")
    cache = load_json(CACHE, {})
    overrides = {}
    if OVERRIDES.exists():
        with open(OVERRIDES, encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                if row.get("lat") and row.get("lng"):
                    overrides[row["id"]] = (float(row["lat"]), float(row["lng"]))

    stats = {"override": 0, "address": 0, "address_village": 0, "keyword": 0, "fail": 0, "region_mismatch": 0}
    for i, f in enumerate(forests):
        if f["id"] in overrides:
            f["lat"], f["lng"] = overrides[f["id"]]
            f["geocode_method"] = "override"
            stats["override"] += 1
            continue
        found = None
        for step, (kind, q) in enumerate(queries(f)):
            if not q:
                continue
            ck = f"{'kakao' if kakao_key else 'vworld'}|{kind}|{q}"
            if ck not in cache:
                try:
                    if kakao_key:
                        cache[ck] = kakao(kind, q, kakao_key)
                    elif kind == "address":
                        cache[ck] = vworld(q, vworld_key)
                    else:
                        cache[ck] = None
                except requests.RequestException as e:
                    # 오류는 캐시에 남기지 않는다 (남기면 다음 실행에서도 '못 찾음'으로 건너뜀)
                    resp = getattr(e, "response", None)
                    if resp is not None and resp.status_code in (401, 403):
                        save_json(CACHE, cache)
                        raise SystemExit(f"API 키 또는 권한 문제로 중단합니다: {resp.text[:200]}")
                    print(f"  요청 실패 {q}: {e}")
                    continue
                time.sleep(0.05)
            res = cache[ck]
            if res and in_korea(res[0], res[1]):
                method = kind if kind == "keyword" else ("address" if step == 0 else "address_village")
                found = (res[0], res[1], res[2], method)
                break
        if found:
            f["lat"], f["lng"], f["geocode_matched"], f["geocode_method"] = found
            stats[found[3]] += 1
            if f["sigungu"] and f["sigungu"] not in (found[2] or ""):
                f["flags"].append("위치 확인 필요")
                stats["region_mismatch"] += 1
        else:
            f["lat"] = f["lng"] = None
            f["geocode_method"] = "fail"
            stats["fail"] += 1
        if i % 100 == 0:
            save_json(CACHE, cache)
            print(f"  {i}/{len(forests)}")
    save_json(CACHE, cache)
    save_json(WORK / "forests_clean.json", forests)
    save_json(WORK / "geocode_report.json", stats)

    # 사람 확인용 시트: 이야기 후보 + 확인이 필요한 것
    with open(WORK / "geocode_check.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["id", "숲 이름", "원본 주소", "찾은 위치", "방법", "위도", "경도", "지도에서 보기", "확인(O/X)", "메모"])
        for f in forests:
            if not (f["story_candidate"] or "위치 확인 필요" in f["flags"] or f["geocode_method"] == "fail"):
                continue
            link = f"https://map.kakao.com/link/map/{quote(f['name'])},{f['lat']},{f['lng']}" if f["lat"] else ""
            w.writerow([f["id"], f["name"], f["address"], f.get("geocode_matched", ""), f["geocode_method"],
                        f["lat"], f["lng"], link, "", ""])
    print("좌표 변환 결과:", stats)
    print("사람 확인용 시트 -> data/work/geocode_check.csv (틀린 곳은 data/geocode_overrides.csv 에 적고 다시 실행)")


if __name__ == "__main__":
    main()
