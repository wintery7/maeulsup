// 전통마을숲 API를 직접 불러오는 Node.js 예제 (Node 18 이상, 별도 설치 없음)
const KEY = "공공데이터포털_인증키";   // Encoding 키든 Decoding 키든 상관없음
const URL_ = "활용명세에_나온_요청주소";

// 키를 한 번 디코딩한 뒤 URLSearchParams가 다시 인코딩하게 둔다 (이중 인코딩 방지)
const key = decodeURIComponent(KEY);

async function main() {
  const items = [];
  for (let page = 1; page < 20; page++) {
    const qs = new URLSearchParams({ serviceKey: key, pageNo: page, numOfRows: 100 });
    const xml = await (await fetch(`${URL_}?${qs}`)).text();
    // 응답은 XML. 간단히 정규식으로 item을 뽑는다 (실제로는 XML 파서를 쓰는 것이 안전)
    const rows = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map(([, body]) =>
      Object.fromEntries([...body.matchAll(/<(\w+)>([\s\S]*?)<\/\1>/g)]
        .map(([, k, v]) => [k, v.trim() || null])));   // 공백 한 칸 빈 값 정리
    if (!rows.length) break;
    items.push(...rows);
  }
  console.log(items.length, "건");
}
main();
