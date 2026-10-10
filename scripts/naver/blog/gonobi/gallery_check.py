"""gonobi_images_v2 전체 이미지 HTML 갤러리 생성."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from ai_orchestrator.core.config import get_local_data_dir

BASE = get_local_data_dir() / "gonobi_images_v2"
OUT = Path("data/gonobi_gallery.html")

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def make_gallery():
    folders = sorted([f for f in BASE.iterdir() if f.is_dir()])

    # 카테고리별 이미지 목록 (상대경로)
    cats = []
    for folder in folders:
        imgs = sorted([f for f in folder.glob("*") if f.suffix.lower() in IMG_EXTS])
        if imgs:
            cats.append({"name": folder.name, "count": len(imgs), "files": imgs})

    total = sum(c["count"] for c in cats)

    # 사이드바 링크
    sidebar = "\n".join(
        f'<a href="#{c["name"]}" class="side-link">'
        f'<span class="cat-name">{c["name"]}</span>'
        f'<span class="cat-cnt">{c["count"]}</span></a>'
        for c in cats
    )

    # 각 카테고리 섹션
    sections = ""
    for cat in cats:
        imgs_html = ""
        for i, f in enumerate(cat["files"], 1):
            # 파일 URI
            uri = f.resolve().as_uri()
            stem = f.stem
            parts = stem.split("_", 2)
            label = parts[2] if len(parts) > 2 else stem
            size_kb = f.stat().st_size // 1024
            imgs_html += f"""
            <div class="img-card" onclick="openFull('{uri}')">
                <img src="{uri}" loading="lazy" onerror="this.parentElement.classList.add('broken')" />
                <div class="img-info">
                    <div class="img-label" title="{label}">{label[:25]}</div>
                    <div class="img-meta">{size_kb}KB · #{i}</div>
                </div>
            </div>"""

        sections += f"""
        <section id="{cat["name"]}">
            <h2>{cat["name"]} <span class="cnt-badge">{cat["count"]}개</span></h2>
            <div class="grid">{imgs_html}</div>
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>gonobi 이미지 분류 확인 ({total}개)</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Malgun Gothic', sans-serif; background: #f5f5f5; display: flex; }}
#sidebar {{
    width: 200px; min-height: 100vh; background: #1a1a2e; position: fixed;
    top: 0; left: 0; overflow-y: auto; padding: 16px 0;
}}
#sidebar h1 {{ color: #e0e0e0; font-size: 13px; padding: 8px 16px 16px; border-bottom: 1px solid #333; }}
.side-link {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 16px; color: #aaa; text-decoration: none; font-size: 12px;
    transition: background 0.15s;
}}
.side-link:hover {{ background: #2a2a4e; color: #fff; }}
.cat-cnt {{ background: #444; border-radius: 10px; padding: 1px 7px; font-size: 11px; }}
#main {{ margin-left: 200px; padding: 24px; flex: 1; }}
section {{ margin-bottom: 40px; }}
h2 {{ font-size: 18px; margin-bottom: 12px; color: #333; border-left: 4px solid #4a90e2; padding-left: 10px; }}
.cnt-badge {{ background: #4a90e2; color: #fff; border-radius: 12px; padding: 2px 10px; font-size: 13px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }}
.img-card {{
    background: #fff; border-radius: 8px; overflow: hidden;
    cursor: pointer; transition: transform 0.15s; box-shadow: 0 1px 4px rgba(0,0,0,.1);
}}
.img-card:hover {{ transform: scale(1.03); box-shadow: 0 4px 12px rgba(0,0,0,.2); }}
.img-card img {{ width: 100%; height: 130px; object-fit: cover; display: block; }}
.img-card.broken {{ border: 2px solid red; }}
.img-card.broken img {{ display: none; }}
.img-card.broken::after {{ content: '❌ 깨진 이미지'; display: flex; align-items: center; justify-content: center; height: 130px; color: red; font-size: 12px; }}
.img-info {{ padding: 6px 8px; }}
.img-label {{ font-size: 11px; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.img-meta {{ font-size: 10px; color: #999; margin-top: 2px; }}
#lightbox {{
    display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,.85); z-index: 1000; align-items: center; justify-content: center;
}}
#lightbox.show {{ display: flex; }}
#lightbox img {{ max-width: 90vw; max-height: 90vh; border-radius: 4px; }}
#lightbox-close {{ position: fixed; top: 20px; right: 30px; color: #fff; font-size: 36px; cursor: pointer; }}
</style>
</head>
<body>
<div id="sidebar">
    <h1>gonobi 이미지 {total}개</h1>
    {sidebar}
</div>
<div id="main">
    {sections}
</div>
<div id="lightbox" onclick="closeFull()">
    <span id="lightbox-close">✕</span>
    <img id="lightbox-img" src="" />
</div>
<script>
function openFull(uri) {{
    document.getElementById('lightbox-img').src = uri;
    document.getElementById('lightbox').classList.add('show');
}}
function closeFull() {{
    document.getElementById('lightbox').classList.remove('show');
}}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeFull(); }});
// 깨진 이미지 카운트
window.addEventListener('load', () => {{
    const broken = document.querySelectorAll('.broken').length;
    if (broken > 0) console.warn('깨진 이미지:', broken, '개');
}});
</script>
</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"갤러리 생성: {OUT}")
    print(f"총 {total}개 / {len(cats)}개 카테고리")
    return OUT


if __name__ == "__main__":
    out = make_gallery()
    import os

    os.startfile(str(out))  # 로컬 생성 파일을 기본 앱으로 열기(Windows), shell 경유 없음
    print("브라우저에서 열기 완료")
