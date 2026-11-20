"""Google Cloud Text-to-Speech 호출.

GOOGLE_TTS_MODEL 이 있으면 Gemini-TTS(말투 지시 prompt 사용), 비어 있으면 Chirp 3 HD 음성을 쓴다.
문서: https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
      https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
"""
import base64

import requests

from common import env, need_env

URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
MAX_BYTES = 4000  # Gemini-TTS 의 text 한도


def speech(text, path, tone):
    """텍스트를 MP3 로 저장. tone 은 child/adult (말투 지시를 고르는 데 씀)."""
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"글이 너무 깁니다 ({len(text.encode('utf-8'))}바이트, 한도 {MAX_BYTES})")
    model = env("GOOGLE_TTS_MODEL")
    voice = env("GOOGLE_TTS_VOICE", "Sulafat")
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "ko-KR"},
        "audioConfig": {"audioEncoding": "MP3"},
    }
    if model:
        body["voice"].update(name=voice, modelName=model)
        prompt = env(f"GOOGLE_TTS_PROMPT_{tone.upper()}")
        if prompt:
            body["input"]["prompt"] = prompt
    else:
        body["voice"]["name"] = f"ko-KR-Chirp3-HD-{voice}"
        rate = env(f"GOOGLE_TTS_RATE_{tone.upper()}")
        if rate:
            body["audioConfig"]["speakingRate"] = float(rate)  # 0.25~2.0, 1.0 이 기본
    r = requests.post(URL, json=body, timeout=120,
                      headers={"X-Goog-Api-Key": need_env("GOOGLE_TTS_API_KEY")})
    if r.status_code != 200:
        raise RuntimeError(f"Google TTS 오류 {r.status_code}: {r.text[:300]}")
    with open(path, "wb") as f:
        f.write(base64.b64decode(r.json()["audioContent"]))
