"""1단계: 공공데이터포털에서 전통마을숲 데이터를 받아 data/raw/maeulsup_raw.json 으로 저장.

필요한 환경변수 (.env)
  DATA_GO_KR_KEY   공공데이터포털 인증키 (Encoding/Decoding 아무거나)
  MAEULSUP_API_URL 활용명세에 나온 전체 요청 주소 (End Point 뒤에 /오퍼레이션명 포함)
"""
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote

import requests

from common import RAW, need_env, save_json

NUM_OF_ROWS = 100
MAX_PAGES = 30  # 개발계정 일일 트래픽(1,000건) 보호


def main():
    url = need_env("MAEULSUP_API_URL")
    # 인코딩된 키를 그대로 params 에 넣으면 requests 가 한 번 더 인코딩해서 인증 오류가 난다.
    key = unquote(need_env("DATA_GO_KR_KEY"))
    items, total = [], None
    for page in range(1, MAX_PAGES + 1):
        r = requests.get(url, params={"serviceKey": key, "pageNo": page, "numOfRows": NUM_OF_ROWS}, timeout=30)
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            sys.exit(f"XML 파싱 실패 (HTTP {r.status_code}):\n{r.text[:500]}")
        code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
        if page == 1:
            total = int(root.findtext(".//totalCount") or 0)
            print(f"resultCode={code} totalCount={total}")
        page_items = [{c.tag: (c.text if c.text is not None else "") for c in it} for it in root.iter("item")]
        if not page_items:
            break
        items.extend(page_items)
        if total and len(items) >= total:
            break
    if not items:
        sys.exit("받은 레코드가 없습니다. 주소와 인증키를 확인하세요.")
    save_json(RAW / "maeulsup_raw.json", items)
    print(f"{len(items)}건 저장 -> data/raw/maeulsup_raw.json")


if __name__ == "__main__":
    main()
