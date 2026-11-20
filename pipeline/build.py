"""7단계: 서비스용 데이터, 개발자 키트, 데이터 진단 리포트를 만든다.

  web/data/forests.json   전국 마을숲 (지도·검색용)
  web/data/stories.json   검증을 통과한 이야기 (mock 결과는 제외)
  web/data/report.json    데이터 진단·검증 수치 ("데이터 이야기" 페이지)
  kit/data/*              정제 데이터 (JSON, CSV, GeoJSON)
  docs/data-report.md     데이터 진단 리포트
"""
import csv
import json
import re
from collections import defaultdict

from common import DOCS, KIT, WEB, WORK, env, load_json, save_json
from stories import josa, safe_template

PLANT_ALIAS = {"해송": "곰솔", "상수리": "상수리나무", "느티": "느티나무"}


MPEG1_KBPS = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
MPEG2_KBPS = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]


def mp3_seconds(path):
    """MP3 재생 시간(초). 고정 비트레이트라 첫 프레임 헤더의 비트레이트로 계산한다."""
    data = path.read_bytes()
    i = 0
    if data[:3] == b"ID3":
        i = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    while i + 2 < len(data) and not (data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0):
        i += 1
    if i + 2 >= len(data):
        return None
    table = MPEG1_KBPS if (data[i + 1] >> 3) & 3 == 3 else MPEG2_KBPS
    kbps = table[data[i + 2] >> 4]
    return round(len(data) * 8 / (kbps * 1000)) if kbps else None


def first_sentence(text, limit=120):
    text = re.sub(r"\s+", " ", text or "").strip()
    m = re.search(r"^(.+?[.다])\s", text + " ")
    out = m.group(1) if m else text
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + "…"


def original(f, field):
    """원문 보기용: 산림청이 준 글 그대로 (잘린 부분 포함)."""
    t = f[field] or ""
    d = f.get(f"{field}_dropped") or ""
    return (t + " " + d).strip() or None


def main():
    forests = load_json(WORK / "forests_clean.json")
    plants = {p["식물명"]: p for p in load_json(WORK / "plants.json", [])}
    allow_mock = env("ALLOW_MOCK") == "1"
    human = load_json(WORK / "human_review.json", {"items": []})
    rejected = {i["id"] for i in human.get("items", []) if i["verdict"] == "탈락"}

    # ---- 이야기 ----
    stories = {}
    for p in sorted((WORK / "stories").glob("*.json")) if (WORK / "stories").exists() else []:
        r = load_json(p)
        if r.get("mock") and not allow_mock:
            continue
        status = r["status"]
        final = r["final"]
        if r["id"] in rejected:
            final = safe_template(next(f for f in forests if f["id"] == r["id"]))
            status = "template"
        audio = {t: f"audio/{r['id']}_{t}.mp3" if (WEB / "audio" / f"{r['id']}_{t}.mp3").exists() else None
                 for t in ("child", "adult")}
        stories[r["id"]] = {
            "status": status,
            "child": [{"t": s["text"], "k": s["type"][0]} for s in final["child"]["sentences"]],
            "adult": [{"t": s["text"], "k": s["type"][0]} for s in final["adult"]["sentences"]],
            "find": final["find"]["text"],
            "audio": audio,
            "sec": {t: mp3_seconds(WEB / a) if a else None for t, a in audio.items()},
        }

    # ---- 숲 목록 ----
    photos = load_json(WORK / "photos.json", {})  # photos.py: 사람이 확인한 관광공사 사진
    web_forests = []
    for f in forests:
        trees = []
        if f["id"] in stories:
            for sp in f["species_list"]:
                name = PLANT_ALIAS.get(sp, sp)
                if name in plants and name not in [t["name"] for t in trees]:
                    trees.append({"name": name, "note": first_sentence(plants[name]["식물의일생"])})
        web_forests.append({
            "id": f["id"], "name": f["name"], "sido": f["sido"], "sigungu": f["sigungu"],
            "address": f["address"], "species": f["species"] or None,
            "lat": round(f["lat"], 5) if f["lat"] else None, "lng": round(f["lng"], 5) if f["lng"] else None,
            "story": f["id"] in stories,
            "history": original(f, "history"), "culture": original(f, "culture"),
            "cut": bool(f["history_truncated"] or f["culture_truncated"]),
            "trees": trees or None,
            "photo": {k: v for k, v in photos[f["id"]].items() if k in ("file", "thumb", "title", "source", "license")}
            if f["id"] in photos and (WEB / photos[f["id"]]["file"]).exists() else None,
        })
    save_json(WEB / "data" / "forests.json", web_forests)
    save_json(WEB / "data" / "stories.json", stories)

    # ---- 리포트 ----
    diag = load_json(WORK / "diagnosis.json")
    geo = load_json(WORK / "geocode_report.json")
    ver = load_json(WORK / "verify_report.json")
    report = {"diagnosis": diag, "geocode": geo, "verify": ver if ver and (not ver.get("mock") or allow_mock) else None,
              "human_review": {k: v for k, v in human.items() if k != "items"} if human.get("reviewed") else None,
              "stories_published": len(stories),
              "stories_with_audio": sum(1 for s in stories.values() if s["audio"]["child"])}
    save_json(WEB / "data" / "report.json", report)

    # ---- 개발자 키트 데이터 ----
    kit_rows = []
    for f in forests:
        kit_rows.append({
            "id": f["id"], "name": f["name"], "sido": f["sido"], "sigungu": f["sigungu"], "address": f["address"],
            "lat": f["lat"], "lng": f["lng"], "geocode_method": f.get("geocode_method"),
            "species": f["species"] or None, "forest_type": f["forest_type"] or None, "area_raw": f["area_raw"],
            "history": original(f, "history"), "history_truncated": f["history_truncated"],
            "culture": original(f, "culture"), "culture_truncated": f["culture_truncated"],
            "dup_group": f["dup_group"], "flags": f["flags"],
        })
    (KIT / "data").mkdir(parents=True, exist_ok=True)
    save_json(KIT / "data" / "maeulsup_clean.json", kit_rows)
    with open(KIT / "data" / "maeulsup_clean.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(kit_rows[0].keys()))
        w.writeheader()
        for r in kit_rows:
            w.writerow({**r, "flags": "|".join(r["flags"])})
    features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
                 "properties": {k: v for k, v in r.items() if k not in ("lat", "lng")}}
                for r in kit_rows if r["lat"]]
    if features:
        save_json(KIT / "data" / "maeulsup_clean.geojson", {"type": "FeatureCollection", "features": features})

    # 사이트에서 바로 내려받을 수 있게 웹 폴더에도 복사
    import shutil
    (WEB / "kit").mkdir(parents=True, exist_ok=True)
    for p in (KIT / "data").glob("maeulsup_clean.*"):
        shutil.copy(p, WEB / "kit" / p.name)

    write_report_md(diag, geo, ver, human, len(stories))
    print(f"서비스 데이터: 숲 {len(web_forests)}곳, 이야기 {len(stories)}편, 음성 {report['stories_with_audio']}편, "
          f"사진 {sum(1 for f in web_forests if f['photo'])}장")
    print(f"개발자 키트: kit/data/ (좌표 있는 숲 {len(features)}곳)")


def write_report_md(d, geo, ver, human, published):
    n = d["records"]
    lines = [
        "# 전통마을숲 데이터, 직접 써보니",
        "",
        f"산림청 전통마을숲위치도 API에서 {n}건을 받아 서비스를 만들면서 확인한 내용이다. "
        "숫자는 `pipeline/clean.py`가 원본을 직접 세어서 낸 값이고, 같은 스크립트를 돌리면 다시 확인할 수 있다.",
        "",
        "## 글이 255바이트에서 잘린다",
        "",
        f"역사조사내용 {d['truncated'].get('history', 0)}건, 문화조사내용 {d['truncated'].get('culture', 0)}건이 "
        f"한글 인코딩(EUC-KR) 기준 253~254바이트에서 끝난다. 글자 수로는 150자 안팎이다. "
        f"이렇게 끝나는 글 {d['truncated_total']}개 중 마침표로 끝나는 건 {d['truncated_end_with_period']}개뿐이고, "
        "나머지는 '500여본 식', '개최하는'처럼 문장 중간에서 끊긴다. 원본 DB 칸이 255바이트로 잡혀 있는 것으로 보인다.",
        "",
        f"같이 쓴 '숲에 사는 식물 정보'도 마찬가지다. 식물이야기설명 {d['plants']}건이 전부 49~50바이트에서 잘린다.",
        "",
        "우리는 잘린 마지막 문장을 잘라내고 이야기를 만들었다. AI가 끊긴 뒤를 상상으로 채우지 못하게 하려고.",
        "",
        "## 빈 값이 빈칸이 아니라 공백 한 칸으로 온다",
        "",
        f"역사조사내용 {d['empty_pct']['history']}%, 문화조사내용 {d['empty_pct']['culture']}%가 비어 있다. "
        "그런데 빈 값이 공백 한 칸(\" \")으로 와서, 단순히 빈 문자열을 세면 0%로 나온다. 처음에 이걸 몰라서 집계를 다시 했다.",
        "",
        "## '위치도'인데 좌표가 없다",
        "",
        "응답 필드 7개 중 위치 정보는 소재지 주소 텍스트 하나다. 지도에 올리려면 주소를 좌표로 바꾸는 작업을 따로 해야 한다. "
        f"주소 형식도 제각각이다. '전북'처럼 시도를 줄여 쓴 주소가 {d['address_issues'].get('시도 약칭', 0)}건, "
        f"시·군이 빠진 주소가 {d['address_issues'].get('시군구 없음', 0)}건, 시도부터 없는 주소가 "
        f"{d['address_issues'].get('시도 없음', 0)}건이다.",
    ]
    if geo:
        ok = geo["address"] + geo["address_village"] + geo["keyword"] + geo["override"]
        lines += ["", f"좌표 변환 결과: {n}건 중 {ok}건 성공 (주소 그대로 {geo['address']}, 마을 단위 {geo['address_village']}, "
                  f"이름 검색 {geo['keyword']}, 수작업 {geo['override']}), 실패 {geo['fail']}건."]
    lines += [
        "",
        "## 다른 숲인데 설명이 같다",
        "",
        f"역사·문화 글이 완전히 같은 묶음이 {d['dup_groups']}개, {d['dup_records']}건이다. "
        f"예를 들면 {josa(', '.join(d['dup_examples'][0][:3]), ('이', '가'))} 같은 설명을 쓴다. 어느 숲의 이야기인지 알 수 없어서 이야기 대상에서 뺐다.",
        "",
        "## 그 밖에",
        "",
        f"- 구역면적은 명세의 단위 표기와 맞지 않아 보인다. 중앙값 {d['area_median']}, 최대 {d['area_max']}로 m²로 보기엔 너무 작아 헥타르(ha)로 추정한다. 확인 전까지 서비스에 면적을 보여주지 않았다.",
        f"- 숲 이름이 '{d['bad_names'][0]}'처럼 이름으로 보기 어려운 레코드가 있다." if d["bad_names"] else "",
        f"- 글 중간에 '?'로 깨진 글자가 섞인 레코드가 {d['question_mark_corruption']}건 있다. (예: '연중?2회')",
        "- 필드명이 `histrexmnncont` 같은 영문 약어라 뜻을 명세에서 하나씩 찾아야 했다.",
        "- API는 XML만 주고, 식물 정보 파일은 CP949 인코딩이라 Mac 엑셀·구글 시트에서 한글이 깨진다.",
        f"- 주요 수종 이름이 식물 정보 데이터와 잘 안 맞는다. 수종 표기 {d['species_tokens']}개 중 식물 정보에 같은 이름이 있는 건 "
        f"{d['species_matched_plants']}개다. '해송'(식물 정보는 '곰솔'), '상수리'('상수리나무')처럼 표기가 다르고, '팽나무'는 식물 정보에 아예 없다.",
        "",
        "## 그래서 이야기로 만든 숲",
        "",
        f"잘린 문장을 정리하고도 역사·문화 기록이 170자 이상 남고, 중복이 아닌 숲 {d['story_candidates']}곳을 골랐다. "
        "지역별로는 " + ", ".join(f"{k} {v}" for k, v in d["story_candidates_by_sido"]) + "곳이다.",
    ]
    if ver and not ver.get("mock"):
        lines += ["", f"생성한 이야기 {ver['stories']}편 중 {ver['verified']}편이 자동 검증(규칙 검사 + 별도 AI 판정)을 통과했다. "
                  f"한 번에 통과한 건 {ver['passed_first_try']}편, 다시 만든 건 {ver['regenerated']}편이다. "
                  f"끝내 통과하지 못한 {ver['template']}편은 원문을 그대로 옮긴 안전 문구로 대체했다."]
    if human.get("reviewed"):
        lines += ["", f"이야기를 만들지 않은 팀원이 {human['reviewed']}편을 원문과 대조해 검수했다. "
                  f"통과 {human['pass']}, 수정 {human['revise']}, 탈락 {human['reject']}."]
    lines += ["", f"서비스에 올라간 이야기: {published}편", ""]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data-report.md").write_text("\n".join(x for x in lines if x is not None), encoding="utf-8")


if __name__ == "__main__":
    main()
