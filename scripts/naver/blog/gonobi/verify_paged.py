"""카테고리별 20장씩 페이지 단위로 스크린샷 촬영."""

import contextlib
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from ai_orchestrator.core.config import get_local_data_dir
from scripts.browser.agent.agent import BrowserAgent

agent = BrowserAgent()
agent.connect()
page = agent.page

BASE = get_local_data_dir() / "gonobi_images_v2"
OUT = Path("data/gonobi_verify_screenshots")
OUT.mkdir(parents=True, exist_ok=True)

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
PAGE_SIZE = 20

cats = sorted([f for f in BASE.iterdir() if f.is_dir()])
print(f"총 {len(cats)}개 카테고리 검증 시작\n")

issues: list[Any] = []

for cat_dir in cats:
    imgs = sorted([f for f in cat_dir.glob("*") if f.suffix.lower() in IMG_EXTS])
    total = len(imgs)
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    cat_name = cat_dir.name
    cat_out = OUT / cat_name
    cat_out.mkdir(exist_ok=True)

    print(f"[{cat_name}] {total}개 / {pages}페이지")

    for pg in range(pages):
        chunk = imgs[pg * PAGE_SIZE : (pg + 1) * PAGE_SIZE]

        # 인라인 HTML 생성
        cards = ""
        for i, f in enumerate(chunk):
            uri = f.resolve().as_uri()
            label = f.stem.split("_", 2)[-1][:20] if len(f.stem.split("_")) > 2 else f.stem[:20]
            size_kb = f.stat().st_size // 1024
            cards += f"""
            <div style="display:inline-block;width:160px;margin:6px;vertical-align:top;background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.15)">
                <img src="{uri}" style="width:160px;height:120px;object-fit:cover;display:block"
                     onerror="this.style.background='#fee';this.alt='ERROR'" />
                <div style="font-size:10px;padding:4px 6px;color:#555">{label}</div>
                <div style="font-size:9px;padding:0 6px 4px;color:#999">{size_kb}KB</div>
            </div>"""

        html = f"""<html><body style="margin:0;padding:12px;background:#f0f0f0;font-family:sans-serif">
        <h2 style="margin-bottom:10px;color:#333">{cat_name} — {pg + 1}/{pages}페이지 ({pg * PAGE_SIZE + 1}~{min((pg + 1) * PAGE_SIZE, total)}번)</h2>
        <div>{cards}</div></body></html>"""

        tmp = Path("data/_tmp_verify.html")
        tmp.write_text(html, encoding="utf-8")

        page.goto(tmp.resolve().as_uri())
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1.5)

        shot = cat_out / f"page_{pg + 1:03d}.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception as e:  # noqa: BLE001 - 고노비 페이지 검증 스크립트(읽기 전용, 스크린샷 저장) -- 스크린샷 실패는 콘솔에 출력만 하고 다음 페이지 계속, 임시 검증 파일 삭제 실패는 무시
            print(f"  페이지{pg + 1} 스크린샷 실패: {e}")

    print(f"  → 저장: {cat_out}")

# 임시 파일 삭제
# 임시 검증 파일 삭제 실패는 무시(읽기전용 검증 스크립트, 재실행 시 덮어써짐)
with contextlib.suppress(Exception):
    Path("data/_tmp_verify.html").unlink()

print(f"\n완료 — 스크린샷 위치: {OUT}")
