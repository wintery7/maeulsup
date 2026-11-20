# 필드 설명표

## 원본 API 필드 → 키트 필드

| 원본 필드 | 뜻 | 키트 필드 | 주의할 점 |
|---|---|---|---|
| `travllgfrstnm` | 숲 이름 | `name` | '195 동일'처럼 이름이 아닌 값이 섞여 있음 |
| `matrlnmplc` | 소재지 (주소) | `address` | 시도 약칭·누락, 시군구 누락이 있음. 괄호 안에 마을 이름이 들어가기도 함 |
| `mainfoftrnm` | 주요 수종 | `species` | 쉼표로 나열. '외3종', '해송'/'곰솔'처럼 표기가 일정하지 않음 |
| `mainfrtpnm` | 주요 임상 | `forest_type` | 3.7% 비어 있음 |
| `zonearea` | 구역 면적 | `area_raw` | 명세 단위와 안 맞아 보임 (ha로 추정, 미확인) |
| `histrexmnncont` | 역사 조사 내용 | `history` | 63.2% 비어 있음. 약 150자에서 잘림 |
| `clturexmnncont` | 문화 조사 내용 | `culture` | 73.1% 비어 있음. 약 150자에서 잘림 |

## 키트에서 더한 필드

| 필드 | 뜻 |
|---|---|
| `id` | 숲 이름과 주소로 만든 고유 번호 (`mf` + 8자리) |
| `sido` | 시도 짧은 이름 (전남, 경북 …). 주소에 없으면 `null` |
| `sigungu` | 시군구 (진도군, 진주시 …). 주소에 없으면 `null` |
| `lat`, `lng` | 위도, 경도 (WGS84). 못 찾으면 `null` |
| `geocode_method` | 위치를 찾은 방법. `address`(주소 그대로), `address_village`(마을 단위), `keyword`(이름 검색), `override`(사람이 직접 확인), `fail` |
| `history_truncated`, `culture_truncated` | 글이 255바이트 근처에서 잘렸으면 `true` |
| `dup_group` | 다른 숲과 설명이 같으면 같은 번호. 아니면 `null` |
| `flags` | 데이터 문제 표시 목록 (CSV에서는 `|`로 구분) |
