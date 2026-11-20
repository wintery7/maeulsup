"""숲 사진: 이야기가 있는 숲의 사진을 한국관광공사 TourAPI와 국가유산청 공개 API에서 찾는다.

산림청 마을숲 데이터에는 사진이 없다. 그래서 관광공사 관광지 중 숲 좌표에서 MAX_KM 안에 있고
이름이 숲 이름과 맞는 곳을 후보로 뽑는다. 그런데 이름이 맞아도 '월남사지', '지전마을 옛 담장'처럼
숲이 아닌 근처 명소 사진인 경우가 많다. 그래서 사람이 사진을 보고 숲이 찍힌 걸 확인한 것(CHECKED)만 쓴다.

국가유산청: 천연기념물로 지정된 마을숲은 국가유산청에 사진이 있다. 사진마다 공공누리 유형이 달라서
(같은 숲 안에서도 1유형과 4유형이 섞여 있다) 국가유산포털 사진 화면에서 유형을 읽어 확인한다.
사진을 보고 숲이 찍힌 걸 확인한 사진 번호(HERITAGE)만 쓴다.

저작권: 공공누리 제1유형(출처표시), 제3유형(출처표시+변경금지), 제4유형(출처표시+비상업+변경금지)을 쓴다.
제4유형은 이 서비스가 무료·비영리 공모전 출품작이라 쓴다. 유료나 광고가 붙으면 빼야 한다 (2026-11-19 결정).
변경금지 유형이 있어서 사진은 줄이거나 자르지 않고 원본 그대로 저장하고, 화면에서도 자르지 않는다.

  python photos.py            후보 찾기(API) + 확인된 사진 내려받기
  python photos.py --offline  캐시된 응답으로 후보 표만 다시 만들기 (API 호출 없음, 국가유산청 사진은 건너뜀)

결과
  data/work/tour_cache.json   API 응답 캐시
  data/work/photo_check.csv   후보 전체 (사람 확인용, '사용' 칸이 O 인 것만 서비스에 쓴다)
  data/work/photos.json       숲 id -> 사진 정보 (build.py 가 읽음)
  web/photos/<id>.jpg         관광공사 원본 사진
"""
import argparse
import csv
import math
import re
import time
import urllib.parse

import xml.etree.ElementTree as ET

import requests

from common import WEB, WORK, load_json, need_env, save_json

API = "https://apis.data.go.kr/B551011/KorService2/"
MAX_KM = 3.0
CACHE = WORK / "tour_cache.json"
LICENSE = {"Type1": "공공누리 제1유형", "Type3": "공공누리 제3유형"}

# 사진을 직접 보고 숲(나무)이 찍힌 걸 확인한 관광지 contentid (2026-11-19 김민재·Claude 확인)
CHECKED = {
    "2788098": "악양 취간림",
    "2784215": "용전숲",
    "128670": "강주연못 (연못 둘레 숲)",
    "2613122": "고성 장산숲",
    "129220": "영광 법성진 숲쟁이",
    "1627027": "전견훤묘 (왕릉과 둘레 숲)",
}
# 이름이 달라 자동으로 못 찾지만 같은 숲인 경우: 숲 id -> contentid
MANUAL = {"mf471c2bf9": "129220"}  # 밤보실마을 숲쟁이공원 = 영광 법성진 숲쟁이 (법성리, 0.46km)

# 국가유산청: 숲 id -> (유산 이름, 종목코드, 지정번호, 시도코드, 사진 번호). 숲 좌표와 유산 좌표가 0.4km 안이고
# 사진을 직접 보고 숲이 찍힌 걸 확인한 것 (2026-11-19). 동백정은 숲이 찍힌 사진이 4유형뿐이다.
HERITAGE = {
    "mf0fcdd4e9": ("완도 미라리 상록수림", "16", "0003390000000", "36", "1631168"),
    "mf74fbdf05": ("강진 백련사 동백나무 숲", "16", "0001510000000", "36", "1630993"),
    "mfc70b00a2": ("완도 예송리 상록수림", "16", "0000400000000", "36", "1630906"),
    "mf0775353d": ("완도 주도 상록수림", "16", "0000280000000", "36", "1630840"),
    "mf0bb96663": ("함평 향교리 느티나무·팽나무·개서어나무 숲", "16", "0001080000000", "36", "1630958"),
    "mf383fb490": ("장흥 동백정", "31", "0001690000000", "36", "1662159"),  # 제4유형, 소나무 숲 원경
}
KHS_LICENSE = {"1": "공공누리 제1유형", "3": "공공누리 제3유형", "4": "공공누리 제4유형"}


def call(op, key, **params):
    params.update({"MobileOS": "ETC", "MobileApp": "maeulsup", "_type": "json"})
    # 공공데이터포털 키는 이미 인코딩된 형태일 수 있어서 직접 붙인다
    sk = key if "%" in key else urllib.parse.quote(key, safe="")
    url = f"{API}{op}?serviceKey={sk}&{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            items = r.json()["response"]["body"].get("items") or {}
            items = items.get("item", []) if isinstance(items, dict) else []
            return items if isinstance(items, list) else [items]
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()


def km(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


GENERIC = ["마을숲", "숲", "마을", "공원", "유원지", "관광지", "쉼터"]


def core(name):
    """'내미로마을숲(천은사)' -> ['내미로', '천은사'] 처럼 비교용 이름들."""
    parts = [name or ""] + re.findall(r"[(（]([^)）]+)[)）]", name or "")
    out = []
    for p in parts:
        p = re.sub(r"[(（][^)）]*[)）]", "", p)
        p = re.sub(r"[\s·ㆍ,\-]", "", p)
        for g in GENERIC:
            if p.endswith(g) and len(p) - len(g) >= 2:
                p = p[: -len(g)]
        if len(p) >= 2:
            out.append(p)
    return out


def name_match(forest_name, title):
    t = re.sub(r"[\s·ㆍ,\-()（）]", "", title or "")
    return any(c in t for c in core(forest_name)) or any(x in c for c in core(forest_name)
                                                        for x in core(title) if len(x) >= 3)


def fetch(forests, key):
    cache = load_json(CACHE, {})
    for i, f in enumerate(forests, 1):
        if f["id"] in cache:
            continue
        near = call("locationBasedList2", key, mapX=f["lng"], mapY=f["lat"], radius=int(MAX_KM * 1000),
                    numOfRows=100, arrange="E")
        kw = []
        for c in core(f["name"])[:2]:
            kw += call("searchKeyword2", key, keyword=c, numOfRows=30)
        cache[f["id"]] = {"near": near, "keyword": kw}
        save_json(CACHE, cache)
        print(f"  {i}/{len(forests)} {f['name']}: 근처 {len(near)}, 이름 검색 {len(kw)}")
        time.sleep(0.2)
    return cache


def candidates(f, entry):
    """이름이 맞고 MAX_KM 안이며 사진이 있는 관광지, 가까운 순. MANUAL 은 이름 검사 없이 넣는다."""
    seen, out = set(), []
    for it in entry["near"] + entry["keyword"]:
        if it["contentid"] in seen or not it.get("mapy") or not it.get("firstimage"):
            continue
        seen.add(it["contentid"])
        d = km(f["lat"], f["lng"], float(it["mapy"]), float(it["mapx"]))
        if d <= MAX_KM and (name_match(f["name"], it["title"]) or MANUAL.get(f["id"]) == it["contentid"]):
            out.append((d, it))
    return sorted(out, key=lambda x: x[0])


THUMB_W = 640


def make_thumb(src, out):
    """가로 THUMB_W 로 줄인 JPEG. 휴대폰 데이터로 홈 화면을 열 때 사진 무게를 줄이려고."""
    from PIL import Image
    img = Image.open(src).convert("RGB")
    if img.width > THUMB_W:
        img = img.resize((THUMB_W, round(img.height * THUMB_W / img.width)), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=74, optimize=True, progressive=True)


def heritage_photo(fid, out):
    """국가유산청 사진을 확인하고 받는다. 공공누리 1·3·4유형이 아니거나 사진이 없으면 None."""
    name, kd, asno, ct, ccim = HERITAGE[fid]
    q = {"ccbaKdcd": kd, "ccbaAsno": asno, "ccbaCtcd": ct}
    r = requests.get("https://www.khs.go.kr/cha/SearchImageOpenapi.do", params=q, timeout=30)
    url = next((e.text.strip() for e in ET.fromstring(r.content).iter("imageUrl")
                if e.text and e.text.strip().endswith(f"/{ccim}.jpg")), None)
    if not url:
        print(f"  국가유산청 사진 없음: {name} {ccim}")
        return None
    page = requests.get("https://www.heritage.go.kr/heri/cul/imgHeritage.do", params={**q, "ccimId": ccim},
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    types = re.findall(r"licenseType(\d)", page)
    if not types or types[0] not in KHS_LICENSE:
        print(f"  공공누리 유형이 1·3·4가 아님: {name} {ccim} {types}")
        return None
    if not out.exists():
        img = requests.get(url, timeout=30)
        img.raise_for_status()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(img.content)  # 원본 그대로
    return {"file": f"photos/{fid}.jpg", "title": name, "source": "국가유산청", "ccimId": ccim,
            "license": KHS_LICENSE[types[0]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="캐시로 후보 표만 다시")
    args = ap.parse_args()

    story_ids = set(load_json(WEB / "data" / "stories.json", {}))
    forests = [f for f in load_json(WORK / "forests_clean.json") if f["id"] in story_ids and f.get("lat")]
    print(f"이야기 있는 숲 {len(story_ids)}곳 중 좌표 있는 {len(forests)}곳")
    cache = load_json(CACHE, {}) if args.offline else fetch(forests, need_env("DATA_GO_KR_KEY"))

    photos, rows = {}, []
    n_cand = 0
    for f in forests:
        cands = candidates(f, cache.get(f["id"], {"near": [], "keyword": []}))
        n_cand += bool(cands)
        pick = next(((d, it) for d, it in cands
                     if it["contentid"] in CHECKED and it.get("cpyrhtDivCd") in LICENSE), None)
        for d, it in cands:
            rows.append({"id": f["id"], "숲": f["name"], "주소": f["address"], "관광지": it["title"],
                         "contentid": it["contentid"], "거리km": round(d, 2), "저작권": it.get("cpyrhtDivCd") or "",
                         "사진": it["firstimage"], "사용": "O" if pick and pick[1] is it else ""})
        if not pick:
            continue
        d, it = pick
        out = WEB / "photos" / f"{f['id']}.jpg"
        if not args.offline and not out.exists():
            r = requests.get(it["firstimage"], timeout=30)
            r.raise_for_status()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.content)  # 변경금지 유형이 있어서 원본 그대로
        if out.exists():
            photos[f["id"]] = {"file": f"photos/{f['id']}.jpg", "title": it["title"], "source": "한국관광공사",
                               "contentid": it["contentid"], "km": round(d, 2), "license": LICENSE[it["cpyrhtDivCd"]]}

    # 관광공사 사진이 없는 숲만 국가유산청 사진을 쓴다
    old = load_json(WORK / "photos.json", {})
    for fid in HERITAGE:
        if fid in photos:
            continue
        if args.offline:
            if fid in old and old[fid].get("source") == "국가유산청":
                photos[fid] = old[fid]
            continue
        p = heritage_photo(fid, WEB / "photos" / f"{fid}.jpg")
        if p:
            photos[fid] = p

    # 홈 화면용 축소본: 변경이 허용된 제1유형만 만든다 (제3·4유형은 변경금지라 원본만 쓴다)
    for fid, p in photos.items():
        p.pop("thumb", None)
        if p["license"] == "공공누리 제1유형":
            src, thumb = WEB / p["file"], WEB / "photos" / "thumb" / f"{fid}.jpg"
            if not thumb.exists() or thumb.stat().st_mtime < src.stat().st_mtime:
                make_thumb(src, thumb)
            p["thumb"] = f"photos/thumb/{fid}.jpg"

    save_json(WORK / "photos.json", photos)
    with open(WORK / "photo_check.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=["id", "숲", "주소", "관광지", "contentid", "거리km", "저작권", "사진", "사용"])
        w.writeheader()
        w.writerows(rows)
    n_khs = sum(1 for p in photos.values() if p["source"] == "국가유산청")
    print(f"이름 맞는 관광지 사진이 있는 숲 {n_cand}곳. 쓰는 사진 {len(photos)}장 "
          f"(관광공사 {len(photos) - n_khs}, 국가유산청 {n_khs})")
    print("후보 전체: data/work/photo_check.csv")


if __name__ == "__main__":
    main()
