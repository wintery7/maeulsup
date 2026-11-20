"""4단계: 이야기 생성과 검증.

숲마다
  1) 생성 (어린이용, 어른용, 찾아볼 것)
  2) 규칙 검사: 숫자·이름·근거 구절이 원문에 실제로 있는지 코드로 대조
  3) AI 판정: 생성과 따로, 사실 문장마다 원문으로 뒷받침되는지 판정
  4) 떨어지면 문제점을 알려주고 다시 생성 (최대 2번)
  5) 그래도 안 되면 원문을 그대로 옮긴 안전 문구로 대체
결과: data/work/stories/<id>.json, data/work/verify_report.json

사용법
  python stories.py            이야기 후보 전체 (이미 만든 것은 건너뜀)
  python stories.py --limit 10 앞에서 10개만 (샘플 확인용)
  python stories.py --redo <id> 특정 숲 다시 만들기
"""
import argparse
from difflib import SequenceMatcher
import re
from collections import Counter

from common import SIDO_LONG, WORK, load_json, norm_for_match, save_json
from llm import chat_json, is_mock
from prompts import (FIX_SUFFIX, GEN_SYSTEM, JUDGE_SCHEMA, JUDGE_SYSTEM, STORY_SCHEMA,
                     source_block, source_fields)

OUT = WORK / "stories"
MAX_RETRY = 2
LIMITS = {"child": (150, 600), "adult": (120, 550)}
STOP = {"등", "외", "기타", "나무", "숲", "마을", "잡목", "활엽수", "침엽수", "혼효림"}
HANJA = re.compile(r"[\u4e00-\u9fff]")
NUM = re.compile(r"\d[\d,.]*")
CHILD_BAD = re.compile(r"[()]|\d\s*(ha|㎡|평)")  # 어린이용에 넣지 않는 괄호·면적
# 어린이용에 남으면 쉬운 말로 다시 쓰게 하는 말. 사실 검증과 별개인 '말투' 검사라,
# 끝까지 남아도 안전 문구로 떨어뜨리지 않고 사실 검증을 통과한 글 중 가장 나은 것을 쓴다.
HARD_WORDS = ["척박", "비옥", "보존", "조성", "내방객", "관리", "식재", "수령", "비보", "액운", "유래",
              "소재", "풍치", "방풍림", "도모", "꾀하", "단합", "양호", "서식", "연접", "지정"]
OPENER = "이야기를 시작해 볼까요"  # 예전 프롬프트가 매번 넣던 연결 말
PROMPT_VERSION = 3  # 2: 어린이용 풀어쓰기 예시·면적/괄호·같은 시작 문구 금지, 3: 어려운 말 검사 후 다시 쓰기 (2026-11-18)


def build_dictionary(forests, plants):
    """다른 숲 기록에 나오는 나무 이름·지명 사전. 원문에 없는 이름이 섞여 들어갔는지 잡는 데 쓴다."""
    terms = set()
    for f in forests:
        for sp in f["species_list"]:
            if len(sp) >= 2 and sp not in STOP:
                terms.add(sp)
        addr = f["address"]
        for t in re.findall(r"[가-힣]+", addr):
            if len(t) >= 3 and re.search(r"(시|군|구|읍|면|리|동|마을|산)$", t):
                terms.add(t)
    for p in plants:
        if len(p["식물명"]) >= 2:
            terms.add(p["식물명"])
    return sorted(terms - STOP, key=len, reverse=True)


QUOTE_MIN_LEN = 20      # 이보다 짧은 근거 구절은 글자 그대로 일치해야 함 (짧으면 한 글자로 뜻이 바뀌기 쉬움)
QUOTE_MIN_RATIO = 0.9   # 긴 근거 구절은 원문 어딘가와 90% 이상 같으면 인정 (옮겨 적기 실수 허용)


def quote_in_source(quote, n_src):
    """근거 구절이 원문에 있는지. 정규화한 뒤 비교한다.

    목적은 '인용을 지어내지 않았다'를 확인하는 것이라, 긴 구절의 한두 글자 옮겨 적기 실수는 봐준다.
    단 숫자는 원문에 그대로 있어야 한다. 문장 내용이 원문에 맞는지는 AI 판정이 따로 본다.
    """
    q = norm_for_match(quote)
    if q in n_src:
        return True
    if len(q) < QUOTE_MIN_LEN or any(d not in n_src for d in re.findall(r"\d+", q)):
        return False
    best = 0.0
    for size in range(len(q) - 2, len(q) + 3):
        for start in range(0, max(1, len(n_src) - size + 1)):
            best = max(best, SequenceMatcher(None, q, n_src[start:start + size]).ratio())
            if best >= QUOTE_MIN_RATIO:
                return True
    return False


def text_of(part):
    return " ".join(s["text"] for s in part["sentences"])


def rule_check(story, f, dictionary):
    src = source_fields(f)
    src_all = " ".join(src.values())
    n_src = norm_for_match(src_all)
    n_src_digits = re.sub(r"[,\s]", "", src_all)
    problems = []

    def check_terms(text, where):
        for term in dictionary:
            if term in text and norm_for_match(term) not in n_src:
                problems.append(f"{where}: 원문에 없는 이름 '{term}'")

    def check_numbers(text, where):
        for num in NUM.findall(text):
            num = num.rstrip(".,")
            if num and num.replace(",", "") not in n_src_digits:
                problems.append(f"{where}: 원문에 없는 숫자 '{num}'")

    for tone in ("child", "adult"):
        part = story[tone]
        if not part["sentences"]:
            problems.append(f"{tone}: 문장이 없음")
            continue
        for i, sent in enumerate(part["sentences"]):
            where = f"{tone} {i + 1}번 문장"
            t = sent["text"]
            check_numbers(t, where)
            check_terms(t, where)
            if tone == "child" and HANJA.search(t):
                problems.append(f"{where}: 어린이용에 한자가 있음")
            bad = CHILD_BAD.search(t.replace(f["name"], "")) if tone == "child" else None  # 숲 이름 속 괄호는 괜찮음
            if bad:
                problems.append(f"{where}: 어린이용에 괄호나 면적 단위가 있음 '{bad.group()}'")
            if sent["type"] == "narration":
                if re.search(r"\d", t) or HANJA.search(t):
                    problems.append(f"{where}: 연결 문장(narration)에 숫자나 한자가 있음")
            else:
                q = sent["source_quote"].strip()
                if not q:
                    problems.append(f"{where}: 근거 구절(source_quote)이 비어 있음")
                elif not quote_in_source(q, n_src):
                    problems.append(f"{where}: 근거 구절이 원문에 없음 '{q[:30]}'")
        lo, hi = LIMITS[tone]
        length = len(text_of(part))
        if not lo <= length <= hi:
            problems.append(f"{tone}: 길이 {length}자 (기준 {lo}~{hi}자)")
    find = story["find"]
    if not find["target"].strip() or norm_for_match(find["target"]) not in n_src:
        problems.append(f"찾아볼 것: 대상 '{find['target']}'이 원문에 없음")
    if find["source_quote"].strip() and not quote_in_source(find["source_quote"], n_src):
        problems.append("찾아볼 것: 근거 구절이 원문에 없음")
    check_numbers(find["text"], "찾아볼 것")
    check_terms(find["text"], "찾아볼 것")
    if HANJA.search(find["text"]):
        problems.append("찾아볼 것: 한자가 있음")
    return problems


def judge(story, f):
    items = []
    for tone in ("child", "adult"):
        for i, s in enumerate(story[tone]["sentences"]):
            if s["type"] == "fact":
                items.append((f"{tone} {i + 1}번 문장", s["text"]))
    items.append(("찾아볼 것", "[찾아볼 것] " + story["find"]["text"]))
    listing = "\n".join(f"({k}) {t}" for k, (_, t) in enumerate(items))
    user = source_block(f) + "\n[문장 목록]\n" + listing
    res = chat_json(JUDGE_SYSTEM, user, JUDGE_SCHEMA, "fact_judge", model_env="OPENAI_JUDGE_MODEL")
    problems, verdicts = [], res["verdicts"]
    for v in verdicts:
        if v["label"] != "supported" and 0 <= v["index"] < len(items):
            where, text = items[v["index"]]
            problems.append(f"{where}: AI 판정 {v['label']} - {v['reason']}")
    return problems, verdicts


def josa(word, pair):
    """받침에 따라 은/는, 이/가 등을 고른다."""
    ch = word[-1] if word else ""
    has_final = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
    return word + (pair[0] if has_final else pair[1])


def safe_template(f):
    """검증을 끝내 통과하지 못한 숲: 원문을 거의 그대로 옮긴다 (지어낸 내용이 들어갈 수 없게)."""
    region = " ".join(x for x in [SIDO_LONG.get(f["sido"] or "", ""), f["sigungu"] or ""] if x)
    name = re.sub(r"\(.*?\)", "", f["name"]).strip()
    first = f"{josa(name, ('은', '는'))} {region}에 있는 마을숲이에요." if region else f"{josa(name, ('은', '는'))} 마을숲이에요."
    sents = [{"text": first, "type": "fact", "source_field": "name", "source_quote": f["name"]}]
    if f["species"]:
        sents.append({"text": f"주요 나무는 {josa(f['species'], ('이에요', '예요'))}.", "type": "fact",
                      "source_field": "species", "source_quote": f["species"]})
    sents.append({"text": "산림청 기록에는 이렇게 남아 있어요.", "type": "narration",
                  "source_field": "none", "source_quote": ""})
    for fld in ("history", "culture"):
        if f[fld]:
            sents.append({"text": f[fld], "type": "fact", "source_field": fld, "source_quote": f[fld]})
    target = f["species_list"][0] if f["species_list"] else name
    return {"child": {"sentences": sents}, "adult": {"sentences": sents},
            "find": {"text": f"숲에 가면 {josa(target, ('을', '를'))} 찾아볼까요?", "target": target,
                     "source_quote": f["species"] or f["name"]}}


def hard_words(story, f):
    """어린이용에 남은 어려운 말 (숲 이름 속 낱말은 뺀다)."""
    t = text_of(story["child"]).replace(f["name"], "")
    return [w for w in HARD_WORDS if w in t]


def make_story(f, dictionary):
    record = {"id": f["id"], "name": f["name"], "attempts": [], "mock": is_mock(), "prompt_version": PROMPT_VERSION}
    problems = []
    best = None  # 사실 검증은 통과했지만 어려운 말이 남은 글 중 가장 나은 것
    for attempt in range(MAX_RETRY + 1):
        system = GEN_SYSTEM + (FIX_SUFFIX.format(problems="\n".join(f"- {p}" for p in problems)) if problems else "")
        story = chat_json(system, source_block(f), STORY_SCHEMA, "forest_story")
        problems = rule_check(story, f, dictionary)
        verdicts = None
        if not problems:
            problems, verdicts = judge(story, f)
        hard = [] if problems else hard_words(story, f)
        if not problems and hard and (best is None or len(hard) < len(best[1])):
            best = (story, hard)
        record["attempts"].append({"story": story, "problems": problems, "verdicts": verdicts, "hard_words": hard})
        if not problems and not hard:
            record.update(status="verified", final=story)
            return record
        if not problems:  # 사실은 맞음. 어려운 말만 풀어 쓰게 다시
            problems = [f"child: 어린이용에 어려운 말 '{w}' (쉬운 말로 풀어 쓰거나, 꼭 필요하지 않으면 뺀다)" for w in hard]
    if best:
        record.update(status="verified", final=best[0], hard_words_left=best[1])
        return record
    record.update(status="template", final=safe_template(f))
    return record


def needs_rewrite(rec):
    """어린이용에 어려운 말, 괄호, 면적이 남아 있는 이야기 (안전 문구는 제외)."""
    if rec.get("status") != "verified" or rec.get("prompt_version", 1) >= PROMPT_VERSION:
        return False
    t = text_of(rec["final"]["child"]).replace(rec["name"], "")
    return bool(CHILD_BAD.search(t)) or any(w in t for w in HARD_WORDS)


def drop_opener(rec):
    """사실이 없는 연결 문장 중 매번 똑같은 시작 문구만 뺀다. 사실 문장은 건드리지 않는다.
    뺀 뒤 어린이용 길이가 기준보다 짧아지면 빼지 않는다. 뺐으면 True."""
    changed = False
    for tone in ("child", "adult"):
        sents = rec["final"][tone]["sentences"]
        keep = [s for s in sents if not (s["type"] == "narration" and OPENER in s["text"])]
        if len(keep) != len(sents) and len(" ".join(s["text"] for s in keep)) >= LIMITS[tone][0]:
            rec["final"][tone]["sentences"] = keep
            changed = True
    if changed:
        rec["opener_removed"] = True
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", help="숲 id, 쉼표로 여러 개")
    ap.add_argument("--redo-hard", action="store_true", help="어린이용에 어려운 말·괄호·면적이 남은 이야기만 다시 만들기")
    ap.add_argument("--polish", action="store_true", help="만든 이야기에서 매번 똑같은 시작 문구만 빼기 (API 호출 없음)")
    args = ap.parse_args()

    if args.polish:
        n = 0
        for p in sorted(OUT.glob("*.json")):
            rec = load_json(p)
            if drop_opener(rec):
                save_json(p, rec)
                n += 1
        print(f"시작 문구를 뺀 이야기 {n}편")
        return

    forests = load_json(WORK / "forests_clean.json")
    plants = load_json(WORK / "plants.json", [])
    dictionary = build_dictionary(forests, plants)
    targets = [f for f in forests if f["story_candidate"]]
    redo = set(args.redo.split(",")) if args.redo else set()
    if args.redo_hard:
        redo |= {p.stem for p in OUT.glob("*.json") if needs_rewrite(load_json(p))}
        print(f"다시 만들 이야기 {len(redo)}편")
    if redo:
        targets = [f for f in forests if f["id"] in redo]
    if args.limit:
        targets = targets[: args.limit]

    OUT.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(targets, 1):
        path = OUT / f"{f['id']}.json"
        if path.exists() and not redo:
            continue
        try:
            rec = make_story(f, dictionary)
        except Exception as e:  # 한 숲에서 실패해도 나머지는 계속
            print(f"[{i}/{len(targets)}] {f['name']} 실패: {e}")
            continue
        save_json(path, rec)
        print(f"[{i}/{len(targets)}] {f['name']}: {rec['status']} (시도 {len(rec['attempts'])}번)")

    # 전체 검증 통계
    recs = [load_json(p) for p in sorted(OUT.glob("*.json"))]
    first_try = Counter()
    reasons = Counter()
    for r in recs:
        first_try["rule_pass" if not any("AI 판정" not in p for p in r["attempts"][0]["problems"]) else "rule_fail"] += 1
        for a in r["attempts"]:
            for p in a["problems"]:
                kind = "AI 판정" if "AI 판정" in p else re.sub(r"'.*", "", p.split(": ", 1)[-1]).strip()
                reasons[kind] += 1
    report = {
        "stories": len(recs),
        "verified": sum(r["status"] == "verified" for r in recs),
        "template": sum(r["status"] == "template" for r in recs),
        "passed_first_try": sum(r["status"] == "verified" and len(r["attempts"]) == 1 for r in recs),
        "regenerated": sum(len(r["attempts"]) > 1 for r in recs),
        "total_attempts": sum(len(r["attempts"]) for r in recs),
        "first_try_rule_check": dict(first_try),
        "problem_types": reasons.most_common(),
        "mock": any(r.get("mock") for r in recs),
    }
    save_json(WORK / "verify_report.json", report)
    print("검증 결과:", {k: report[k] for k in ("stories", "verified", "template", "passed_first_try", "regenerated")})


if __name__ == "__main__":
    main()
