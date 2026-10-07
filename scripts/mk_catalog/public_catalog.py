"""내부 원가 카탈로그 → 소비자용 공개 카탈로그 생성.

내부 카탈로그(`data/mk_catalog/site/catalog_web.html`)에는 공급가·마진배율이
들어 있어 그대로 공개하면 안 된다. 특히 **제품코드는 마지막 두 블록이 공급가**라
(pricing.py 참조) 코드만 노출돼도 원가가 역산된다.

이 스크립트는 민감 필드를 제거하고 판매가만 남긴 공개용 HTML을 만든다.

노출:     name, size, led, ct, color, features, cat, img, sellPrice
비노출:   code(원가 역산), price(공급가), adjPrice, mult(마진배율), page, src

출력: haehan-ai/public/lighting/catalog.html → https://haehan-ai.kr/lighting/catalog.html
사용: python -m scripts.mk_catalog.public_catalog
"""

from __future__ import annotations

import html as html_mod
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.common.app_paths import resolve_external, sibling_project  # noqa: E402

SRC = _ROOT / "data" / "mk_catalog" / "site" / "catalog_web.html"
DST = resolve_external(
    "HAEHAN_HOMEPAGE_CATALOG", "haehan-ai", "public", "lighting", "catalog.html", base=sibling_project("30. 해한 AI 홈페이지")
)

PUBLIC_FIELDS = ("name", "size", "led", "ct", "color", "features", "cat", "img", "sellPrice")
BIZ_PHONE = "010-7387-6635"


def load_products() -> list[dict]:
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"(?:const|var|let)\s+DATA\s*=\s*(\[.*?\]);", raw, re.S)
    if not m:
        raise RuntimeError("DATA 배열을 찾지 못했습니다")
    return json.loads(m.group(1))


_CODE_IN_PATH = re.compile(r"\d{3}-\d{3}-\d{3,4}-\d{3}")
SRC_IMG_DIR = SRC.parent / "images"
DST_IMG_DIR = DST.parent / "img"


def sanitize(products: list[dict]) -> list[dict]:
    """민감 필드를 제거하고 판매가 있는 제품만 남긴다.

    ⚠️ img 가 base64 가 아니라 파일경로인 제품이 섞여 있는데, 그 경로에
    제품코드가 들어 있다(예: images/283-001-112-800/01.jpg → 공급가 112,800원).
    판매가와 나란히 놓이면 마진이 그대로 역산되므로, 경로형 이미지는
    코드가 드러나지 않는 일련번호 파일명으로 복사해 다시 링크한다.
    """
    from PIL import Image

    DST_IMG_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    seq = 0
    for p in products:
        img = str(p.get("img") or "")
        if not p.get("sellPrice") or not img:
            continue

        item = {k: p.get(k) for k in PUBLIC_FIELDS if p.get(k)}

        if not img.startswith("data:"):
            src = SRC.parent / img
            if not src.exists():
                continue
            seq += 1
            # 원본은 고해상도라 그대로 쓰면 폴더가 130MB를 넘는다.
            # 카탈로그 썸네일 용도이므로 520px·JPEG q78로 줄여 저장(약 18MB).
            name = f"p{seq:04d}.jpg"
            try:
                im = Image.open(src).convert("RGB")
                im.thumbnail((520, 520), Image.Resampling.LANCZOS)
                im.save(DST_IMG_DIR / name, "JPEG", quality=78, optimize=True)
            except Exception:  # noqa: BLE001 - 공개 카탈로그용 썸네일 생성 - 개별 이미지 처리 실패 시 continue로 해당 항목만 skip(읽기전용 이미지 가공)
                continue
            item["img"] = f"img/{name}"

        # 어떤 필드에도 제품코드가 남지 않았는지 최종 확인
        if any(_CODE_IN_PATH.search(str(v)) for v in item.values()):
            continue
        out.append(item)
    return out


def render(products: list[dict]) -> str:
    cats = sorted({p.get("cat", "기타") for p in products})
    payload = json.dumps(products, ensure_ascii=False, separators=(",", ":"))
    chips = "".join(f'<button class="chip" data-cat="{html_mod.escape(c)}">{html_mod.escape(c)}</button>' for c in cats)
    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>조명 카탈로그 | 반딧불 조명</title>
<meta name="description" content="LED 다운라이트·라인조명·펜던트 등 조명 제품 카탈로그. 남양주 다산동 조명 시공 문의.">
<style>
:root{{--bg:#faf9f7;--surface:#fff;--border:#e6e2da;--ink:#1c1a17;--muted:#6f6a61;--accent:#c2660e;--accent-soft:#fdf1e2}}
@media(prefers-color-scheme:dark){{:root{{--bg:#15130f;--surface:#1e1b16;--border:#332e25;--ink:#f2ede4;--muted:#a89f90;--accent:#e8934a;--accent-soft:#33240f}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Malgun Gothic",sans-serif;line-height:1.6}}
header{{padding:28px 20px 20px;border-bottom:1px solid var(--border);background:var(--surface)}}
.wrap{{max-width:1100px;margin:0 auto}}
h1{{margin:0 0 6px;font-size:22px;letter-spacing:-.02em}}
.sub{{margin:0;color:var(--muted);font-size:14px}}
.cta{{display:inline-block;margin-top:14px;padding:10px 18px;border-radius:8px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700;font-size:14px}}
.tools{{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 20px;border-bottom:1px solid var(--border)}}
input[type=search]{{width:100%;padding:11px 14px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--ink);font-size:15px}}
.chips{{display:flex;gap:6px;overflow-x:auto;padding:10px 0 2px;scrollbar-width:none}}
.chips::-webkit-scrollbar{{display:none}}
.chip{{flex:0 0 auto;padding:7px 13px;border-radius:99px;border:1px solid var(--border);background:var(--surface);color:var(--muted);font-size:13px;cursor:pointer}}
.chip.on{{background:var(--accent-soft);border-color:var(--accent);color:var(--accent);font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px;padding:18px 20px 60px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}}
.card img{{width:100%;aspect-ratio:1;object-fit:contain;background:#fff;display:block}}
.info{{padding:10px 11px 12px}}
.nm{{font-size:13px;font-weight:700;margin:0 0 5px;line-height:1.35}}
.sp{{font-size:12px;color:var(--muted);margin:0 0 2px}}
.pr{{margin-top:7px;font-size:15px;font-weight:800;color:var(--accent)}}
.count{{padding:0 20px;color:var(--muted);font-size:13px}}
footer{{padding:26px 20px 46px;border-top:1px solid var(--border);background:var(--surface);color:var(--muted);font-size:13px}}
footer b{{color:var(--ink)}}
</style></head><body>
<header><div class="wrap">
<h1>조명 카탈로그</h1>
<p class="sub">다운라이트 · 라인조명 · 펜던트 · 벽등 등 {len(products):,}개 제품<br>표시 가격은 제품 단가이며, 시공비는 현장에 따라 별도입니다.</p>
<a class="cta" href="tel:{BIZ_PHONE}">📞 조명 상담 {BIZ_PHONE}</a>
</div></header>
<div class="tools"><div class="wrap">
<input type="search" id="q" placeholder="제품명·규격 검색 (예: 3인치, 라인, 펜던트)">
<div class="chips"><button class="chip on" data-cat="">전체</button>{chips}</div>
</div></div>
<div class="wrap"><p class="count" id="count"></p><div class="grid" id="grid"></div></div>
<footer><div class="wrap">
<p><b>반딧불 조명</b> · 20년 현장경력 · 전기공사산업기사 · 소방전기기사</p>
<p>📍 경기도 남양주시 다산동 6143외1필지 다산현대프리미어캠퍼스 2층 에이씨02-043호</p>
<p>📞 {BIZ_PHONE} · 평면도 보내주시면 조명 배치 3D 시안을 무료로 만들어 드립니다.</p>
</div></footer>
<script>
const D={payload};
const g=document.getElementById('grid'),c=document.getElementById('count'),q=document.getElementById('q');
let cat='',kw='';
const won=n=>n.toLocaleString('ko-KR')+'원';
function draw(){{
  const f=D.filter(p=>(!cat||p.cat===cat)&&(!kw||((p.name||'')+(p.size||'')+(p.led||'')).toLowerCase().includes(kw)));
  c.textContent=f.length.toLocaleString()+'개 제품';
  g.innerHTML=f.slice(0,300).map(p=>`<div class="card"><img loading="lazy" src="${{p.img}}" alt="${{p.name}}">
  <div class="info"><p class="nm">${{p.name}}</p>
  ${{p.size?`<p class="sp">${{p.size}}</p>`:''}}${{p.led?`<p class="sp">${{p.led}}</p>`:''}}${{p.ct?`<p class="sp">${{p.ct}}</p>`:''}}
  <div class="pr">${{won(p.sellPrice)}}</div></div></div>`).join('');
}}
document.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');cat=b.dataset.cat;draw();
}});
q.oninput=e=>{{kw=e.target.value.trim().toLowerCase();draw();}};
draw();
</script></body></html>"""


def main() -> None:
    products = sanitize(load_products())
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(render(products), encoding="utf-8")
    mb = DST.stat().st_size / 1024 / 1024
    print(f"생성 완료: {DST}")
    print(f"  제품 {len(products):,}개 / {mb:.1f}MB")
    print("  비노출 확인: code·price·adjPrice·mult 제거됨")


if __name__ == "__main__":
    main()
