"""OpenAI 호출을 한곳에 모은 모듈.

모델 이름은 코드에 박지 않고 .env 에서 읽는다. OpenAI 모델은 자주 바뀌니
https://platform.openai.com/docs/models 에서 현재 권장 모델을 확인해 넣는다.

MOCK_LLM=1 이면 OpenAI 를 부르지 않고 원문을 그대로 잘라 쓰는 가짜 결과를 돌려준다.
파이프라인 흐름을 확인하는 용도이며, mock 결과는 build 단계에서 서비스에 올라가지 않는다.
"""
import json
import re

from common import env, need_env

_client = None


def is_mock():
    return env("MOCK_LLM") == "1"


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=need_env("OPENAI_API_KEY"))
    return _client


def chat_json(system, user, schema, schema_name, model_env="OPENAI_MODEL"):
    """Structured Outputs(JSON Schema, strict)로 응답을 받아 dict 로 돌려준다."""
    if is_mock():
        return _mock(schema_name, user)
    model = env(model_env) or need_env("OPENAI_MODEL")
    resp = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
    )
    msg = resp.choices[0].message
    if getattr(msg, "refusal", None):
        raise RuntimeError(f"모델이 응답을 거절함: {msg.refusal}")
    return json.loads(msg.content)


# ---- 오프라인 테스트용 가짜 응답 ----
def _mock(schema_name, user):
    def field(label):
        m = re.search(rf"{label}\((\w+)\): (.*)", user)
        return m.group(2).replace("(기록이 여기서 끊김)", "").strip() if m else ""
    if schema_name == "forest_story":
        name, hist = field("숲 이름"), field("역사 기록")
        first = hist.split(".")[0][:60] if hist and hist != "기록 없음" else name
        sents = [
            {"text": f"[MOCK] {name} 이야기예요.", "type": "fact", "source_field": "name", "source_quote": name},
            {"text": "[MOCK] 자, 들어 볼까요?", "type": "narration", "source_field": "none", "source_quote": ""},
            {"text": f"[MOCK] {first}", "type": "fact", "source_field": "history", "source_quote": first},
        ]
        sp = field("주요 나무").split(",")[0].strip()
        return {"child": {"sentences": sents}, "adult": {"sentences": sents},
                "find": {"text": f"[MOCK] {sp}를 찾아볼까요?", "target": sp, "source_quote": sp}}
    if schema_name == "fact_judge":
        n = user.count("\n(")
        return {"verdicts": [{"index": i, "label": "supported", "reason": "mock"} for i in range(n)]}
    raise ValueError(schema_name)
