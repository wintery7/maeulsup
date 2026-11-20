"""이야기 생성과 사실 판정에 쓰는 프롬프트와 JSON 스키마."""
from common import SIDO_LONG

CUT_MARK = "(기록이 여기서 끊김)"

GEN_SYSTEM = """너는 산림청 전통마을숲 조사 기록을, 차 안에서 아이에게 들려줄 1분짜리 이야기로 옮기는 작가다.

반드시 지킬 것
1. 사실은 [원문]에 있는 것만 쓴다. 원문에 없는 연도, 숫자, 인물, 전설, 장소, 나무 이름, 행사, 크기는 절대 쓰지 않는다. 그럴듯해 보여도 덧붙이지 않는다.
2. 원문이 "(기록이 여기서 끊김)"으로 끝나면, 끊긴 뒤의 내용을 짐작해서 잇지 않는다. 끊기기 직전의 미완성 구절도 쓰지 않는다.
3. 숫자는 원문 표기 그대로 쓴다. "1700년경"을 "300년 전"처럼 계산해서 바꾸지 않는다.
4. 말투만 바꾼다.
   - child(어린이용): 7~10세가 듣기 쉬운 다정한 존댓말("~했대요", "~이에요"). 한자와 괄호는 빼고, 어려운 말은 쉬운 말로 풀어 쓴다. 풀어 쓸 때 새로운 사실을 보태지 않는다. 250~450자.
     풀어 쓰기 예: 방풍림 → 바람을 막아 주는 숲, 조성하다 → 만들다, 식재하다 → 심다, 수령 → 나무 나이, 보존하다 → 잘 지키다,
     비옥하다 → 땅이 기름지다, 척박하다 → 땅이 메마르다, 당산제·동제 → 마을을 지켜 달라고 비는 제사, 보호수 → 특별히 지키기로 정한 나무,
     내방객 → 찾아오는 사람, 유래 → 생겨난 까닭, 단결을 도모하다 → 함께 힘을 모으다, 이조 → 조선.
     어린이용에는 면적(ha, ㎡, 평)과 "관리와 보존이 필요하다" 같은 행정 문서 문장은 넣지 않는다(빼는 것은 괜찮다).
     이야기는 여러 편을 이어서 듣는다. "자, 이야기를 시작해 볼까요?", "차 안에서 천천히 들려줄게요" 같은 어느 숲에나 붙는 연결 말은 쓰지 않는다. 연결 말(narration)은 꼭 필요할 때 한 문장까지만.
     위치는 시·군까지만 말한다. 번지 숫자(예: 235-2)는 넣지 않는다.
   - adult(어른용): 차분한 해설 말투. 200~400자.
5. 첫 문장에서 숲 이름과 어느 지역(시·군)에 있는지 알려준다.
6. 문장마다 type 을 붙인다.
   - fact: 원문에 근거한 사실. source_field 에 근거 항목(name, address, species, history, culture)을, source_quote 에 근거가 된 원문 구절을 적는다.
     source_quote 규칙: 그 문장의 근거가 되는 짧은 구절 하나(보통 10~50자)를 원문에서 글자 그대로 복사한다. 띄어쓰기·조사·어미를 한 글자도 바꾸지 않는다. 항목 이름표("역사 기록(history):" 같은 것)와 "(기록이 여기서 끊김)"은 원문이 아니므로 넣지 않는다. 기록 전체를 통째로 붙이지 않는다.
   - narration: 사실이 없는 연결 말("자, 이야기를 시작해 볼까요?"). source_field 는 none, source_quote 는 빈 문자열. narration 에는 숫자, 지명, 나무 이름, 사람 이름을 넣지 않는다.
7. find: 숲에 도착하면 아이가 찾아볼 것 한 가지. target 은 원문에 나오는 눈에 보이는 대상(나무, 연못, 정자, 돌 등)을 원문 표기 그대로, text 는 아이에게 건네는 한 문장("~를 찾아볼까요?"), source_quote 는 그 대상이 나온 짧은 원문 구절(위 source_quote 규칙과 같음). 마땅한 대상이 없으면 주요 나무 중 하나를 고른다.
"""

FIX_SUFFIX = """

이전에 쓴 이야기가 검증에서 아래 문제로 떨어졌다. 같은 문제가 없도록 처음부터 다시 써라.
{problems}
"근거 구절이 원문에 없음"은 source_quote 가 원문과 글자 단위로 일치하지 않는다는 뜻이다. 이름표나 "(기록이 여기서 끊김)"을 빼고, 짧은 구절을 원문에서 그대로 복사한다.
"""

SENT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "type", "source_field", "source_quote"],
    "properties": {
        "text": {"type": "string"},
        "type": {"type": "string", "enum": ["fact", "narration"]},
        "source_field": {"type": "string", "enum": ["name", "address", "species", "history", "culture", "none"]},
        "source_quote": {"type": "string"},
    },
}
STORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["child", "adult", "find"],
    "properties": {
        "child": {"type": "object", "additionalProperties": False, "required": ["sentences"],
                  "properties": {"sentences": {"type": "array", "items": SENT}}},
        "adult": {"type": "object", "additionalProperties": False, "required": ["sentences"],
                  "properties": {"sentences": {"type": "array", "items": SENT}}},
        "find": {"type": "object", "additionalProperties": False, "required": ["text", "target", "source_quote"],
                 "properties": {"text": {"type": "string"}, "target": {"type": "string"},
                                "source_quote": {"type": "string"}}},
    },
}

JUDGE_SYSTEM = """너는 사실 검증 담당자다. [원문]과 [문장 목록]을 받는다.
각 문장이 원문만으로 뒷받침되는지 판정한다. 말투나 쉬운 말로 풀어 쓴 것은 괜찮지만, 원문에 없는 정보가 하나라도 들어 있으면 unsupported, 원문과 다르면 contradicted 다.

괜찮은 것 (supported): 뜻이 같은 풀어쓰기와 말투 변화
- 어려운 말을 쉬운 말로: "방풍림" → "바람을 막아 주는 숲", "꾀하는" → "도모하는", "함께 힘을 모으는",
  "조성" → "만들다", "식재" → "심다", "수령" → "나무 나이", "보존" → "잘 지키다", "비옥한" → "기름진",
  "척박한" → "메마른", "당산제·동제" → "마을을 지켜 달라고 비는 제사", "내방객" → "찾아오는 사람",
  "단결을 도모" → "함께 힘을 모으다", "이조" → "조선"
- 원문의 일부 내용(면적, 관리 필요성 등)을 빼고 말하지 않은 것
- 존댓말·해설 말투, 과거형과 현재형 바꾸기("지냈다" ↔ "지낸대요"), 문장 나누기·합치기
안 되는 것: 원문에 없는 연도·숫자·인물·전설·장소·나무 이름·행사·크기·이유를 덧붙이는 것, 원문과 다른 내용

"[찾아볼 것]"으로 표시된 문장은 아이에게 숲에서 무언가를 찾아보자고 권하는 말이다.
권유하는 형식 자체("~를 찾아볼까요?")는 문제 삼지 않는다. 그 문장에 나온 대상과 꾸밈말(나이, 크기, 위치 등)이 원문에 있는지만 판정한다.
- supported: 원문으로 뒷받침됨
- unsupported: 원문에 없는 내용이 들어 있음 (짐작, 과장, 덧붙임 포함)
- contradicted: 원문과 어긋남
reason 에는 판정 이유를 한 문장으로 쓴다.
"""
JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["index", "label", "reason"],
            "properties": {"index": {"type": "integer"},
                           "label": {"type": "string", "enum": ["supported", "unsupported", "contradicted"]},
                           "reason": {"type": "string"}}}},
    },
}


def source_fields(f):
    """원문 항목들 (검증에도 같은 값을 쓴다)."""
    region = " ".join(x for x in [SIDO_LONG.get(f["sido"] or "", ""), f["sigungu"] or ""] if x)
    return {
        "name": f["name"],
        "address": f"{f['address']} ({region})" if region else f["address"],
        "species": f["species"] or "",
        "history": f["history"] or "",
        "culture": f["culture"] or "",
    }


def source_block(f):
    src = source_fields(f)
    hist = src["history"] + (f" {CUT_MARK}" if f["history_truncated"] and src["history"] else "")
    cult = src["culture"] + (f" {CUT_MARK}" if f["culture_truncated"] and src["culture"] else "")
    return (
        "[원문]\n"
        f"숲 이름(name): {src['name']}\n"
        f"위치(address): {src['address']}\n"
        f"주요 나무(species): {src['species'] or '기록 없음'}\n"
        f"역사 기록(history): {hist or '기록 없음'}\n"
        f"문화 기록(culture): {cult or '기록 없음'}\n"
    )
