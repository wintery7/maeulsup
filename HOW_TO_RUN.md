# 실행과 배포 순서

처음부터 끝까지 이 순서대로 하면 된다. 명령은 모두 `pipeline` 폴더 안에서 실행한다.

## 0. 준비 (한 번만)

Python 3.10 이상이 필요하다.

```bash
cd pipeline
pip install -r requirements.txt
```

프로젝트 맨 위 폴더에서 `.env.example`을 복사해 `.env`를 만들고 값을 채운다. `.env`는 절대 GitHub에 올리지 않는다 (`.gitignore`에 들어 있음).

필요한 키

| 키 | 어디서 | 언제 필요 |
|---|---|---|
| `KAKAO_REST_KEY` | developers.kakao.com → 내 애플리케이션 → 앱 키의 REST API 키. 앱 설정에서 카카오맵(로컬) 사용 설정이 필요할 수 있음 | 3단계 좌표 |
| `VWORLD_KEY` (카카오 대신) | vworld.kr → 오픈API → 인증키 발급 | 3단계 좌표 |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_JUDGE_MODEL` | platform.openai.com. 모델 이름은 Models 문서에서 현재 권장 모델 확인 | 4단계 |
| `GOOGLE_TTS_API_KEY` | Google Cloud 콘솔에서 Cloud Text-to-Speech API 사용 설정 후 API 및 서비스 → 사용자 인증 정보 → API 키. 결제 계정 연결 필요 | 6단계 |
| `DATA_GO_KR_KEY`, `MAEULSUP_API_URL` | 공공데이터포털 | 1단계 (선택) |

## 1. 데이터 받기 (선택)

`data/raw/maeulsup_raw.json`에 이미 받은 원본(1,106건)이 들어 있다. 최신 데이터로 다시 받고 싶을 때만 실행한다.

```bash
python fetch.py
```

## 2. 정리와 진단

```bash
python clean.py
```

빈 값 정리, 시도·시군구 분리, 잘린 글 처리, 중복 표시, 이야기 후보 선정(약 100곳)을 한다. 진단 수치는 `data/work/diagnosis.json`에 남는다.

## 3. 주소를 좌표로

```bash
python geocode.py
```

끝나면 `data/work/geocode_check.csv`가 생긴다. **세림 담당**: 이야기 후보 숲과 '위치 확인 필요' 숲이 들어 있으니, '지도에서 보기' 링크를 눌러 위치가 맞는지 확인한다. 틀린 곳은 `data/geocode_overrides.csv`에 아래처럼 적고 `geocode.py`를 다시 돌린다.

```
id,lat,lng,memo
mf1b58fa33,34.xxxxx,126.xxxxx,카카오맵에서 직접 찾음
```

## 4. 이야기 만들기와 자동 검증

먼저 10편만 만들어 본다.

```bash
python stories.py --limit 10
```

`data/work/stories/` 안의 결과를 세림과 같이 본다. 말투나 길이를 바꾸고 싶으면 `prompts.py`의 `GEN_SYSTEM`을 고치고, 그 10편을 지우고 다시 만든다. OpenAI 사용량 페이지에서 10편에 든 비용을 보고 전체(약 10배) 비용을 가늠한다.

괜찮으면 전체를 만든다. 이미 만든 숲은 건너뛴다.

```bash
python stories.py
```

특정 숲만 다시 만들 때: `python stories.py --redo <숲 id>` (쉼표로 여러 개)

프롬프트를 고친 뒤 어린이용에 어려운 말·괄호·면적이 남은 이야기만 다시 만들 때: `python stories.py --redo-hard` (`--limit 5`로 먼저 확인)

예전 프롬프트로 만든 이야기에서 매번 똑같은 시작 문구("자, 이야기를 시작해 볼까요?")만 뺄 때: `python stories.py --polish` (API를 부르지 않음)

## 5. 사람 검수 (세림 담당)

```bash
python review.py --n 30
```

`data/work/review/review.html`을 세림에게 보낸다. 브라우저로 열어서 판정하고 'CSV로 저장'을 누르면 `검수결과.csv`가 내려받아진다. 그 파일을 받아서

```bash
python review.py --import 검수결과.csv
```

'탈락' 판정을 받은 숲은 서비스에서 원문 그대로 옮긴 안전 문구로 바뀐다. 다시 만들고 싶으면 `stories.py --redo <id>` 후 다시 검수한다.

## 6. 음성 만들기

```bash
python tts.py --limit 2   # 먼저 2곳만 만들어 듣고 목소리·말투 확인
python tts.py
```

음성은 Chirp 3 HD(월 100만 자 무료)로 만든다. 목소리는 `.env`의 `GOOGLE_TTS_VOICE`로 바꾼다. 말투 지시(`GOOGLE_TTS_PROMPT_*`)는 `GOOGLE_TTS_MODEL`에 Gemini-TTS 모델을 넣었을 때만 쓰이고, 이쪽은 유료다. 바꾼 뒤에는 `web/audio/`의 샘플 파일을 지우고 다시 만든다.

시작하기 전에 보낼 글자 수를 보여 주고, 한 번에 30만 자를 넘으면 시작하지 않는다(무료 한도는 월 100만 자, 104편 전체가 약 5만 자). 이미 만든 음성은 건너뛰고, 이야기를 다시 만들어 글이 바뀐 것만 다시 만든다(`data/work/audio_manifest.json`).

`web/audio/`에 숲마다 `_child.mp3`, `_adult.mp3`가 생긴다. 시간이 없으면 `python tts.py --only child`로 어린이용만 만든다. 음성 파일이 없는 이야기는 브라우저 음성으로 읽어 준다 (화면이 꺼지면 멈출 수 있음).

## 6-1. 숲 사진 (선택)

```bash
python photos.py
```

마을숲 데이터에는 사진이 없어서 한국관광공사 TourAPI(공공데이터포털 「한국관광공사_국문 관광정보 서비스_GW」, 활용신청 필요, `DATA_GO_KR_KEY`와 같은 키)에서 찾는다. 숲에서 3km 안에 있고 이름이 맞는 관광지가 후보인데, 이름이 맞아도 절터나 담장처럼 숲이 아닌 사진이 많다. 그래서 사진을 보고 숲이 찍힌 걸 확인한 것만 `photos.py`의 `CHECKED`에 적어 두고 그것만 쓴다. 후보 전체는 `data/work/photo_check.csv`에 있다. 관광공사 사진이 없는 숲은 국가유산청 공개 API(키 필요 없음)에서 천연기념물로 지정된 숲의 사진을 쓴다. 같은 숲 사진이라도 공공누리 유형이 사진마다 달라서(1유형과 4유형이 섞임) 실행할 때 국가유산포털 사진 화면에서 유형을 다시 읽고, 1·3·4유형이 아니면 쓰지 않는다(4유형은 비상업 조건이라 서비스가 무료인 동안만). 쓸 사진 번호는 `HERITAGE`에 적어 둔다. 공공누리 제3·4유형(변경금지)이 섞여 있어서 사진은 원본 그대로 `web/photos/`에 저장하고 숲 화면에서도 자르지 않는다. 홈 화면용으로는 제1유형만 가로 640px 축소본을 `web/photos/thumb/`에 만든다(Pillow 필요). 사진을 바꾸지 않았으면 `python photos.py --offline`으로 API 호출 없이 다시 만들 수 있다.

## 7. 서비스 데이터와 키트 만들기

```bash
python build.py
```

`web/data/`, `web/kit/`, `kit/data/`, `docs/data-report.md`가 새로 만들어진다.

## 8. 내 컴퓨터에서 확인

```bash
cd ../web
python -m http.server 8000
```

브라우저에서 http://localhost:8000 을 연다. 휴대폰으로 보려면 같은 와이파이에서 `http://내컴퓨터IP:8000`.

## 9. 배포

`web` 폴더만 올리면 된다. 서버 코드가 없는 정적 사이트라 아무 정적 호스팅이나 된다.

**가장 쉬운 방법: Netlify Drop**
app.netlify.com/drop 에 로그인하고 `web` 폴더를 끌어다 놓는다. 주소가 바로 나온다. 사이트 설정에서 이름을 `maeulsup` 같은 걸로 바꿀 수 있다.

**GitHub + Vercel**
1. 이 프로젝트를 GitHub에 올린다 (`.env`가 안 올라갔는지 꼭 확인).
2. vercel.com → Add New → Project → 저장소 선택
3. Root Directory를 `web`으로, Framework Preset은 Other, Build Command는 비워 둔다.
4. Deploy

어느 쪽이든 업로드 용량 제한이 있으니 `web` 폴더 크기를 먼저 확인하고, 크면 어른용 음성을 빼거나 각 서비스의 제한을 확인한다.

배포 후 `web/assets/config.js`의 `githubUrl`에 저장소 주소를 넣고 다시 배포하면 '개발자 키트' 페이지에 링크가 생긴다.

## 10. 배포 후 확인 (세림 담당)

- 시크릿 창, 다른 기기(아이폰, 안드로이드)에서 열리는가
- "진도", "진도군", "진도 가는 길"을 넣어도 결과가 나오는가
- 이야기가 없는 지역(예: 인천)을 넣으면 안내가 나오는가
- 휴대폰 화면을 끈 채로 '처음부터 이어서 듣기'가 끝까지 재생되는가
- 듣기 시작하고 10초쯤 뒤 비행기 모드로 바꿔도 목록 끝까지 이어지는가
- '지금 있는 곳 근처 이야기 듣기'가 위치 권한을 묻고, 허용하면 가까운 순 목록이 나오는가
- 지도가 나오는가, 길찾기 링크가 맞는 곳을 가리키는가
- 화면 맨 아래 출처와 AI 고지가 보이는가

## 문제가 생기면

- `환경변수 ... 가 없습니다`: `.env` 파일 위치(프로젝트 맨 위 폴더)와 이름을 확인
- 공공데이터 API 인증 오류: 키를 넣을 때 따옴표나 공백이 섞이지 않았는지 확인
- OpenAI 오류에 `response_format`이 나오면: Structured Outputs를 지원하는 모델인지 문서에서 확인
- 오프라인으로 흐름만 확인하고 싶으면: `MOCK_LLM=1 python stories.py --limit 3` (Windows PowerShell은 `$env:MOCK_LLM="1"; python stories.py --limit 3`). 가짜 결과라 서비스에는 안 올라가고, 확인이 끝나면 `data/work/stories/` 안의 파일을 지운다.
