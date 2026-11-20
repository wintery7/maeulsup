"""6단계: 사람 검수.

  python review.py              검수용 페이지 만들기 -> data/work/review/review.html (브라우저로 열기)
  python review.py --n 15       표본 수 바꾸기 (기본 30)
  python review.py --import 검수결과.csv   검수 결과 집계 -> data/work/human_review.json

검수자는 이야기를 만든 사람이 아닌 사람이 맡는다. 페이지에서 판정하고 'CSV로 저장'을 누르면 결과 파일이 내려받아진다.
"""
import argparse
import csv
import html
import json
import random
from collections import Counter

from common import WORK, load_json, save_json
from prompts import source_fields

PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>마을숲 이야기 검수</title>
<style>
body{{font-family:system-ui,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;margin:0;background:#f3f5f1;color:#1d2b22}}
header{{position:sticky;top:0;background:#1f3d2b;color:#fff;padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
header button{{font-size:15px;padding:8px 14px;border:0;border-radius:6px;background:#e9f2e3;color:#1f3d2b;font-weight:700;cursor:pointer}}
main{{max-width:1100px;margin:0 auto;padding:16px}}
.item{{background:#fff;border:1px solid #d5ded3;border-radius:8px;margin:14px 0;padding:14px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
h2{{font-size:18px;margin:0 0 8px}} h3{{font-size:14px;margin:10px 0 4px;color:#4a5d50}}
.src{{font-size:14px;line-height:1.6;background:#f6f8f4;padding:10px;border-radius:6px}}
.s{{display:block;margin:3px 0;line-height:1.6}} .narr{{color:#6b7b70}}
.fact::before{{content:"사실";font-size:11px;background:#dfeee0;color:#2c5d3a;border-radius:4px;padding:1px 5px;margin-right:6px}}
.narr::before{{content:"연결";font-size:11px;background:#eee;color:#666;border-radius:4px;padding:1px 5px;margin-right:6px}}
.judge{{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;align-items:center}}
.judge label{{font-size:15px}} textarea{{width:100%;min-height:44px;font:inherit;margin-top:6px}}
.tpl{{font-size:12px;color:#9a5a3c}}
</style></head><body>
<header><b>마을숲 이야기 검수 ({n}건)</b><span id="done">0 / {n} 완료</span>
<button onclick="saveCsv()">CSV로 저장</button></header>
<main>
<p>왼쪽 원문과 오른쪽 이야기를 나란히 보고 판정해 주세요. <b>탈락</b>: 원문에 없는 사실, 원문과 다른 사실, 끊긴 문장을 상상으로 이은 경우.
<b>수정</b>: 아이가 이해하기 어려운 말, 찾아볼 것이 부적절, 길이·말투 문제. 수정·탈락은 이유를 한 줄 적어 주세요.</p>
{items}
</main>
<script>
const ITEMS={ids};
function update(){{let d=0;for(const id of ITEMS){{if(document.querySelector(`input[name="v_${{id}}"]:checked`))d++;}}
document.getElementById('done').textContent=d+' / '+ITEMS.length+' 완료';}}
document.addEventListener('change',update);
function saveCsv(){{const rows=[['id','숲 이름','판정','이유']];
for(const id of ITEMS){{const v=document.querySelector(`input[name="v_${{id}}"]:checked`);
const r=document.getElementById('r_'+id).value.replace(/\\n/g,' ');
rows.push([id,document.getElementById('n_'+id).textContent,v?v.value:'',r]);}}
const csv='\\ufeff'+rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(',')).join('\\n');
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}}));
a.download='검수결과.csv';a.click();}}
</script></body></html>"""

ITEM = """<section class="item"><h2 id="n_{id}">{name}</h2>{tpl}
<div class="grid"><div><h3>산림청 원문</h3><div class="src">{src}</div></div>
<div><h3>어린이용 이야기</h3>{child}<h3>찾아볼 것</h3><span class="s">{find}</span>
<h3>어른용 이야기</h3>{adult}</div></div>
<div class="judge"><label><input type="radio" name="v_{id}" value="통과"> 통과</label>
<label><input type="radio" name="v_{id}" value="수정"> 수정</label>
<label><input type="radio" name="v_{id}" value="탈락"> 탈락</label></div>
<textarea id="r_{id}" placeholder="수정·탈락 이유"></textarea></section>"""


def sentences(part):
    return "".join(f'<span class="s {"fact" if s["type"] == "fact" else "narr"}">{html.escape(s["text"])}</span>'
                   for s in part["sentences"])


def make_page(n):
    forests = {f["id"]: f for f in load_json(WORK / "forests_clean.json")}
    recs = [load_json(p) for p in sorted((WORK / "stories").glob("*.json"))]
    recs = [r for r in recs if r["status"] == "verified" and not r.get("mock")] or recs
    random.Random(20261116).shuffle(recs)
    recs = recs[:n]
    items = []
    for r in recs:
        f = forests[r["id"]]
        src = source_fields(f)
        src_html = "<br>".join(f"<b>{k}</b>: {html.escape(v or '기록 없음')}" for k, v in
                               [("숲 이름", src["name"]), ("위치", src["address"]), ("주요 나무", src["species"]),
                                ("역사", src["history"] + (" (기록이 여기서 끊김)" if f["history_truncated"] else "")),
                                ("문화", src["culture"] + (" (기록이 여기서 끊김)" if f["culture_truncated"] else ""))])
        st = r["final"]
        items.append(ITEM.format(id=r["id"], name=html.escape(f["name"]), src=src_html,
                                 child=sentences(st["child"]), adult=sentences(st["adult"]),
                                 find=html.escape(st["find"]["text"]),
                                 tpl='<div class="tpl">자동 검증을 통과하지 못해 원문 그대로 옮긴 안전 문구입니다</div>'
                                 if r["status"] == "template" else ""))
    out = WORK / "review" / "review.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.format(n=len(recs), items="\n".join(items), ids=json.dumps([r["id"] for r in recs])),
                   encoding="utf-8")
    print(f"검수 페이지 {len(recs)}건 -> {out}")


def import_result(path):
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))
    judged = [r for r in rows if r["판정"]]
    c = Counter(r["판정"] for r in judged)
    result = {"reviewed": len(judged), "pass": c["통과"], "revise": c["수정"], "reject": c["탈락"],
              "items": [{"id": r["id"], "name": r["숲 이름"], "verdict": r["판정"], "reason": r["이유"]}
                        for r in judged if r["판정"] != "통과"]}
    save_json(WORK / "human_review.json", result)
    print(f"검수 {len(judged)}건: 통과 {c['통과']}, 수정 {c['수정']}, 탈락 {c['탈락']}")
    print("탈락·수정된 숲은 'python stories.py --redo <id>' 로 다시 만들 수 있습니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--import", dest="imp")
    a = ap.parse_args()
    import_result(a.imp) if a.imp else make_page(a.n)
