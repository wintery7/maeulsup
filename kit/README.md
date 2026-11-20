# 전통마을숲 개발자 키트

산림청 「전통마을숲위치도(산림공간정보 1:25000)」 데이터를 바로 쓸 수 있게 정리한 것이다.
원본 데이터의 이용허락범위는 '제한 없음'이다. 쓸 때는 출처(산림청, 공공데이터포털)를 밝혀 주면 된다.

## 5분 만에 써 보기

1. `data/maeulsup_clean.csv`를 엑셀이나 구글 시트로 연다. 한글이 깨지지 않는다 (UTF-8).
2. 지도에 올리려면 `data/maeulsup_clean.geojson`을 geojson.io, QGIS, 카카오맵 API 등에 그대로 넣는다.
3. 프로그램에서 쓰려면 `data/maeulsup_clean.json`을 읽는다.

```python
import json
forests = json.load(open("data/maeulsup_clean.json", encoding="utf-8"))
jeonnam = [f for f in forests if f["sido"] == "전남" and f["history"]]
print(len(jeonnam), jeonnam[0]["name"], jeonnam[0]["lat"], jeonnam[0]["lng"])
```

원본 API를 직접 부르는 예제는 `examples/`에 있다.

## 원본과 다른 점

| 원본에서 | 키트에서 |
|---|---|
| 빈 값이 공백 한 칸(" ") | `null` |
| 필드명이 `histrexmnncont` 같은 약어 | `history` 같은 이름. 대응표는 [FIELDS.md](FIELDS.md) |
| 위치가 주소 텍스트뿐 | `lat`, `lng` (WGS84). 어떤 방법으로 찾았는지 `geocode_method` |
| 시도 표기가 제각각 ('전북', '전라북도') | `sido`는 짧은 이름으로 통일 ('전북'), `sigungu` 따로 |
| 잘렸는지 알 수 없음 | `history_truncated`, `culture_truncated` |
| 중복 설명 표시 없음 | 같은 설명을 쓰는 숲끼리 같은 `dup_group` 번호 |
| XML | JSON, CSV(UTF-8), GeoJSON |

원문 글(`history`, `culture`)은 손대지 않았다. 잘린 글도 잘린 그대로 두고 표시만 했다.

## 알아 두면 좋은 데이터 문제

- 역사·문화 조사 글이 EUC-KR 기준 253~254바이트(약 150자)에서 잘려 있다. `*_truncated`가 `true`면 문장이 중간에 끊겼다고 보면 된다.
- 역사 조사 내용은 63%, 문화 조사 내용은 73%가 비어 있다.
- 다른 숲인데 설명이 같은 기록이 18묶음 72건 있다 (`dup_group`).
- `area_raw`(구역면적)는 명세의 단위와 맞지 않아 보인다. 값 범위로는 헥타르(ha)로 추정되지만 확인되지 않았다.
- `geocode_method`가 `keyword`면 숲 이름으로 찾은 위치라 오차가 있을 수 있다. `fail`이면 위치를 못 찾은 것이다.
- `flags`에 '이상한 이름', '물음표 깨짐', '위치 확인 필요' 등이 표시되어 있다.

자세한 수치는 [../docs/data-report.md](../docs/data-report.md)에 있다.

## 정리 과정을 다시 돌리려면

`../pipeline/clean.py`(정리), `../pipeline/geocode.py`(좌표), `../pipeline/build.py`(내보내기) 순서다. 방법은 [../HOW_TO_RUN.md](../HOW_TO_RUN.md).
