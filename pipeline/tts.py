"""5단계: 이야기를 MP3 음성으로 만든다 (web/audio/<id>_child.mp3, <id>_adult.mp3).

차 안에서 휴대폰 화면이 꺼져도 끊기지 않게 하려고 브라우저 음성 대신 파일로 만든다.
Google Cloud Text-to-Speech 를 쓴다 (google_tts.py).
필요한 환경변수 (.env): GOOGLE_TTS_API_KEY, GOOGLE_TTS_MODEL, GOOGLE_TTS_VOICE,
GOOGLE_TTS_PROMPT_CHILD, GOOGLE_TTS_PROMPT_ADULT (.env.example 참고)
이미 만든 파일은 건너뛴다. 이야기 글이나 음성 설정(목소리·속도 등)이 바뀐 것만 다시 만든다.
"""
import argparse
import hashlib

from common import WEB, WORK, env, load_json, save_json
from google_tts import speech

AUDIO = WEB / "audio"
MANIFEST = WORK / "audio_manifest.json"  # 파일 이름 -> 만들 때 쓴 글의 해시
MAX_CHARS_PER_RUN = 300_000              # 실수로 여러 번 돌려도 무료 한도(월 100만 자)를 넘지 않게


def digest(text, tone):
    """글과 음성 설정(모델·목소리·속도·말투 지시)을 합친 해시. 둘 중 하나라도 바뀌면 다시 만든다."""
    t = tone.upper()
    settings = [env("GOOGLE_TTS_MODEL") or "", env("GOOGLE_TTS_VOICE") or "",
                env(f"GOOGLE_TTS_RATE_{t}") or "", env(f"GOOGLE_TTS_PROMPT_{t}") or ""]
    return hashlib.sha256("\n".join([text, *settings]).encode("utf-8")).hexdigest()[:16]


def spoken_text(story, tone):
    text = " ".join(s["text"] for s in story[tone]["sentences"])
    if tone == "child":
        text += " " + story["find"]["text"]
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["child", "adult"], help="한쪽 말투만 만들기")
    ap.add_argument("--limit", type=int, help="앞에서 N곳만 (샘플 확인용)")
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS_PER_RUN,
                    help=f"이번 실행에서 보낼 글자 수 한도 (기본 {MAX_CHARS_PER_RUN:,}자, 넘으면 시작하지 않음)")
    args = ap.parse_args()
    AUDIO.mkdir(parents=True, exist_ok=True)
    recs = [load_json(p) for p in sorted((WORK / "stories").glob("*.json"))]
    recs = [r for r in recs if not r.get("mock")]
    if args.limit:
        recs = recs[:args.limit]
    tones = [args.only] if args.only else ["child", "adult"]

    # 만들 것 고르기: 파일이 없거나, 이야기 글이 바뀐 것만 (이야기를 다시 만들면 음성도 다시)
    manifest = load_json(MANIFEST, {})
    todo = []
    for i, r in enumerate(recs, 1):
        for tone in tones:
            name = f"{r['id']}_{tone}.mp3"
            text = spoken_text(r["final"], tone)
            if (AUDIO / name).exists() and manifest.get(name) == digest(text, tone):
                continue
            todo.append((i, r, tone, name, text))
    chars = sum(len(t[4]) for t in todo)
    print(f"만들 음성 {len(todo)}개, 보낼 글자 {chars:,}자 (Chirp 3 HD 무료 한도: 월 1,000,000자)")
    if chars > args.max_chars:
        raise SystemExit(f"한도 {args.max_chars:,}자를 넘어서 시작하지 않습니다. 정말 만들려면 --max-chars 를 올리세요.")

    made = 0
    for i, r, tone, name, text in todo:
        try:
            speech(text, AUDIO / name, tone)
            manifest[name] = digest(text, tone)
            save_json(MANIFEST, manifest)
            made += 1
            print(f"[{i}/{len(recs)}] {r['name']} {tone}")
        except Exception as e:
            print(f"[{i}/{len(recs)}] {r['name']} {tone} 실패: {e}")
    print(f"새로 만든 음성 파일 {made}개")


if __name__ == "__main__":
    main()
