"""문제 이미지 261개 HTML로 시각 확인."""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = Path("data/gonobi_images_v2")
OUT = Path("data/gonobi_problems.html")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

problems = []
for cat_dir in sorted(BASE.iterdir()):
    if not cat_dir.is_dir():
        continue
    for f in sorted(cat_dir.glob("*")):
        if f.suffix.lower() not in IMG_EXTS:
            continue
        try:
            img = Image.open(f)
            w, h = img.size
            ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 99
            reason = None
            if w < 100 or h < 100:
                reason = f"소형({w}x{h})"
            elif ratio > 8:
                reason = f"긴비율({w}x{h}, 1:{ratio:.0f})"
            if reason:
                problems.append((cat_dir.name, f, w, h, reason))
        except Exception as e:
            problems.append((cat_dir.name, f, 0, 0, f"깨짐({e})"))

# 카테고리별 그룹
from collections import defaultdict  # noqa: E402

by_cat = defaultdict(list)
for cat, f, w, h, reason in problems:
    by_cat[cat].append((f, w, h, reason))

sections = ""
for cat, items in sorted(by_cat.items()):
    cards = ""
    for f, w, h, reason in items:
        uri = f.resolve().as_uri()
        label = f.stem.split("_", 2)[-1][:25] if len(f.stem.split("_")) > 2 else f.stem[:25]
        size_kb = f.stat().st_size // 1024
        color = "#fee" if "소형" in reason else "#fef3cd"
        cards += f"""
        <div style="display:inline-block;width:180px;margin:6px;vertical-align:top;
                    background:{color};border-radius:6px;overflow:hidden;
                    box-shadow:0 1px 4px rgba(0,0,0,.15);border:1px solid #ddd">
            <img src="{uri}" style="width:180px;height:140px;object-fit:contain;
                         display:block;background:#fff;padding:4px"
                 onerror="this.style.background='#f88'" />
            <div style="font-size:10px;padding:4px 6px;color:#333;font-weight:bold">{reason}</div>
            <div style="font-size:9px;padding:0 6px;color:#666">{label}</div>
            <div style="font-size:9px;padding:0 6px 4px;color:#999">{size_kb}KB</div>
        </div>"""
    sections += f"""
    <section style="margin-bottom:32px">
        <h2 style="font-size:16px;margin-bottom:8px;color:#333;
                   border-left:4px solid #e74c3c;padding-left:10px">
            {cat} — {len(items)}개 문제
        </h2>
        <div>{cards}</div>
    </section>"""

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>문제 이미지 확인 ({len(problems)}개)</title>
<style>
body {{ font-family: 'Malgun Gothic',sans-serif; background:#f5f5f5; padding:20px; }}
h1 {{ margin-bottom:6px; }}
.legend {{ margin-bottom:20px; font-size:13px; color:#555; }}
.legend span {{ display:inline-block; width:14px; height:14px;
               border-radius:3px; margin-right:4px; vertical-align:middle; }}
</style>
</head>
<body>
<h1>문제 이미지 {len(problems)}개 확인</h1>
<div class="legend">
    <span style="background:#fee"></span> 소형(100px미만) — 아이콘/썸네일 의심 &nbsp;&nbsp;
    <span style="background:#fef3cd"></span> 긴비율(1:8이상) — 상세페이지 캡처 의심
</div>
{sections}
</body>
</html>"""

OUT.write_text(html, encoding="utf-8")
print(f"생성: {OUT} ({len(problems)}개)")

import subprocess  # noqa: E402

subprocess.Popen(["start", "", str(OUT.resolve())], shell=True)
