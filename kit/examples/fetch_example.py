"""전통마을숲 API를 직접 불러서 JSON으로 저장하는 가장 짧은 예제.

pip install requests
"""
import json
import xml.etree.ElementTree as ET
from urllib.parse import unquote

import requests

KEY = "공공데이터포털_인증키"          # Encoding 키든 Decoding 키든 상관없음
URL = "활용명세에_나온_요청주소"         # End Point 뒤에 /오퍼레이션명까지

# 인코딩된 키를 그대로 params에 넣으면 requests가 한 번 더 인코딩해서 인증 오류가 난다.
key = unquote(KEY)

items = []
for page in range(1, 20):
    r = requests.get(URL, params={"serviceKey": key, "pageNo": page, "numOfRows": 100}, timeout=30)
    root = ET.fromstring(r.text)                       # 응답은 XML
    rows = [{c.tag: (c.text or "").strip() or None     # 빈 값이 공백 한 칸으로 오므로 정리
             for c in it} for it in root.iter("item")]
    if not rows:
        break
    items.extend(rows)

json.dump(items, open("maeulsup.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(len(items), "건 저장")
