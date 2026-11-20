"""2단계: 원본 정리 + 데이터 진단.

- 공백 한 칸으로 오는 빈 값 정리, 주소에서 시도/시군구 분리
- 255바이트(EUC-KR) 근처에서 잘린 글 표시, 끊긴 마지막 문장 잘라내기
- 다른 숲인데 글이 같은 중복 묶음 표시, 이상한 숲 이름 표시
- 이야기로 만들 후보 선정
결과: data/work/forests_clean.json, data/work/diagnosis.json
"""
import csv
import hashlib
import re
import statistics
from collections import Counter, defaultdict

from common import RAW, SIDO_SHORT, WORK, FIELD_MAP, cp949_bytes, load_json, s, save_json

TRUNC_BYTES = 252          # 이 바이트 이상이면 잘린 것으로 본다 (실측 253~254)
STORY_MIN_CHARS = 170      # 정리 후 역사+문화 글자 수가 이 이상이면 이야기 후보
SIGUNGU_RE = re.compile(r"^[가-힣]+(시|군|구)$")
CORRUPT_RE = re.compile(r"[가-힣0-9]\?[가-힣0-9]")


def make_id(name, address):
    return "mf" + hashlib.sha1(f"{name}|{address}".encode("utf-8")).hexdigest()[:8]


def parse_address(addr):
    """주소 문자열에서 시도(짧은 이름)와 시군구를 뽑는다. 못 찾으면 None."""
    tokens = re.sub(r"\(.*?\)", " ", addr).split()
    sido = sigungu = None
    issues = []
    if tokens and tokens[0] in SIDO_SHORT:
        sido = SIDO_SHORT[tokens[0]]
        if tokens[0] == sido:
            issues.append("시도 약칭")
        rest = tokens[1:]
    else:
        issues.append("시도 없음")
        rest = tokens
    for t in rest[:2]:
        if SIGUNGU_RE.match(t):
            sigungu = t
            break
    if sigungu is None:
        issues.append("시군구 없음")
    return sido, sigungu, issues


def trim_truncated(text):
    """잘린 글에서 끊긴 마지막 부분을 잘라낸다. (정리된 글, 잘라낸 부분)"""
    cut = text.rfind(".")
    if cut >= 40:
        return text[: cut + 1].strip(), text[cut + 1 :].strip()
    cut = text.rfind(",")
    if cut >= 40:
        return text[:cut].strip(), text[cut + 1 :].strip()
    cut = text.rfind(" ")
    if cut >= 40:
        return text[:cut].strip(), text[cut + 1 :].strip()
    return "", text


def split_species(sp):
    sp = re.sub(r"외\s*\d+\s*종", "", sp)
    return [t.strip() for t in re.split(r"[,，/·ㆍ\s]+", sp) if t.strip()]


def main():
    raw = load_json(RAW / "maeulsup_raw.json")
    n = len(raw)
    whitespace_only = Counter()
    empty = Counter()
    forests = []
    for r in raw:
        row = {}
        for src, dst in FIELD_MAP.items():
            v = r.get(src)
            if v is not None and v != "" and s(v) == "":
                whitespace_only[dst] += 1
            row[dst] = s(v)
            if not row[dst]:
                empty[dst] += 1
        forests.append(row)

    # 중복 텍스트 묶음
    groups = defaultdict(list)
    for i, f in enumerate(forests):
        if f["history"] or f["culture"]:
            groups[(f["history"], f["culture"])].append(i)
    dup_groups = [idx for idx in groups.values() if len(idx) > 1]
    dup_of = {}
    for gi, idx in enumerate(dup_groups):
        for i in idx:
            dup_of[i] = gi

    trunc = Counter()
    trunc_bytes = Counter()
    long_hist_end_period = [0, 0]
    corrupt = 0
    addr_issues = Counter()
    bad_names = []
    areas = []
    cleaned = []
    for i, f in enumerate(forests):
        sido, sigungu, issues = parse_address(f["address"])
        for it in issues:
            addr_issues[it] += 1
        flags = []
        texts = {}
        for field in ("history", "culture"):
            t = f[field]
            b = cp949_bytes(t)
            is_trunc = b >= TRUNC_BYTES
            if is_trunc:
                trunc[field] += 1
                trunc_bytes[b] += 1
                trimmed, dropped = trim_truncated(t)
            else:
                trimmed, dropped = t, ""
            if is_trunc:
                long_hist_end_period[0] += 1
                long_hist_end_period[1] += t.endswith(".")
            texts[field] = {"text": trimmed, "truncated": is_trunc, "dropped": dropped}
        if CORRUPT_RE.search(f["history"] + f["culture"] + f["name"]):
            corrupt += 1
            flags.append("물음표 깨짐")
        name_bad = bool(re.match(r"^\d", f["name"])) or "동일" in f["name"] or len(f["name"]) < 2
        if name_bad:
            bad_names.append(f["name"])
            flags.append("이상한 이름")
        if i in dup_of:
            flags.append("중복 텍스트")
        try:
            area = float(f["area"]) if f["area"] else None
        except ValueError:
            area = None
        if area is not None:
            areas.append(area)
        story_len = len(texts["history"]["text"]) + len(texts["culture"]["text"])
        candidate = (
            story_len >= STORY_MIN_CHARS and i not in dup_of and not name_bad and sido is not None
        )
        cleaned.append({
            "id": make_id(f["name"], f["address"]),
            "name": f["name"],
            "address": f["address"],
            "sido": sido,
            "sigungu": sigungu,
            "species": f["species"],
            "species_list": split_species(f["species"]),
            "forest_type": f["forest_type"],
            "area_raw": area,
            "history": texts["history"]["text"] or None,
            "history_truncated": texts["history"]["truncated"],
            "history_dropped": texts["history"]["dropped"] or None,
            "culture": texts["culture"]["text"] or None,
            "culture_truncated": texts["culture"]["truncated"],
            "culture_dropped": texts["culture"]["dropped"] or None,
            "story_chars": story_len,
            "story_candidate": candidate,
            "dup_group": dup_of.get(i),
            "flags": flags,
            "lat": None,
            "lng": None,
        })

    # 식물 정보
    plants = []
    plant_story_bytes = Counter()
    with open(RAW / "plants_cp949.csv", encoding="cp949", newline="") as fp:
        for row in csv.DictReader(fp):
            plant_story_bytes[cp949_bytes(row["식물이야기설명"] or "")] += 1  # 원본 그대로 잰다
            plants.append({k: s(v) for k, v in row.items()})
    plant_names = {p["식물명"] for p in plants}
    plant_blank_en = sum(1 for p in plants if not p["영문명"])
    sp_total = sp_hit = 0
    sp_miss = Counter()
    for f in cleaned:
        for sp in f["species_list"]:
            sp_total += 1
            if sp in plant_names:
                sp_hit += 1
            else:
                sp_miss[sp] += 1

    cands = [f for f in cleaned if f["story_candidate"]]
    diag = {
        "records": n,
        "empty_pct": {k: round(empty[k] / n * 100, 1) for k in FIELD_MAP.values()},
        "whitespace_only": dict(whitespace_only),
        "truncated": dict(trunc),
        "truncated_bytes_top": trunc_bytes.most_common(5),
        "truncated_total": long_hist_end_period[0],
        "truncated_end_with_period": long_hist_end_period[1],
        "dup_groups": len(dup_groups),
        "dup_records": sum(len(g) for g in dup_groups),
        "dup_examples": [[forests[i]["name"] for i in g] for g in dup_groups[:5]],
        "bad_names": bad_names,
        "question_mark_corruption": corrupt,
        "address_issues": dict(addr_issues),
        "area_median": statistics.median(areas) if areas else None,
        "area_max": max(areas) if areas else None,
        "story_candidates": len(cands),
        "story_candidates_by_sido": Counter(f["sido"] for f in cands).most_common(),
        "plants": len(plants),
        "plant_story_bytes": plant_story_bytes.most_common(5),
        "plant_blank_english_name": plant_blank_en,
        "species_tokens": sp_total,
        "species_matched_plants": sp_hit,
        "species_unmatched_top": sp_miss.most_common(10),
    }
    save_json(WORK / "forests_clean.json", cleaned)
    save_json(WORK / "plants.json", plants)
    save_json(WORK / "diagnosis.json", diag)
    print(f"정리 완료: {n}건, 이야기 후보 {len(cands)}건")
    for k in ("empty_pct", "truncated", "truncated_bytes_top", "dup_groups", "dup_records",
              "question_mark_corruption", "address_issues", "story_candidates_by_sido",
              "species_matched_plants", "species_tokens"):
        print(f"  {k}: {diag[k]}")


if __name__ == "__main__":
    main()
