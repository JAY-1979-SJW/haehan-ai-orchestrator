"""팝업 DOM 진단 (Playwright 네이티브 is_visible 기준).

EUM 사이트는 pop_modal_cont 템플릿 12개를 항상 DOM에 로드하지만,
실제 화면에 표시되는 팝업은 Playwright의 is_visible()로 판단해야 합니다.

이 스크립트는:
  - DOM 카운트 (참고용)
  - 실제 화면에 보이는 팝업 (Playwright is_visible)
  - 실제 화면 스크린샷
을 모두 보고합니다.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page

from scripts.popup_detector import _looks_like_popup_window

page = get_page()

print("=" * 70)
print("현재 페이지 URL:", page.url)
print("=" * 70)

# 0. BrowserContext의 모든 페이지 (별도 창 팝업 포함)
ctx = page.context
all_pages = ctx.pages
print(f"\n[BrowserContext 전체 페이지] {len(all_pages)}개")
popup_windows = []
for i, p in enumerate(all_pages):
    try:
        url = p.url
    except Exception:
        url = "(unavailable)"
    if p is page:
        marker = "[현재작업]"
        reason = ""
    else:
        is_popup, reason = _looks_like_popup_window(p)
        marker = f"[팝업창:{reason}]" if is_popup else "[일반]"
        if is_popup:
            popup_windows.append(p)
    print(f"  {marker} [{i}] {url[:90]}")
print(f"\n  ⚠  별도 창 팝업: {len(popup_windows)}개" if popup_windows else "  ✓ 별도 창 팝업 없음")

# 1. 스크린샷
shot_path = ROOT / "data" / "popup_diag.png"
page.screenshot(path=str(shot_path), full_page=False)
print(f"\n[스크린샷] {shot_path.name}")

# 2. DOM 카운트 (참고용 — EUM은 빈 템플릿을 항상 12개 로드)
popups = page.locator(".pop_modal_cont")
dimmed = page.locator(".dimmed")
print(f"\n[DOM 카운트 — 참고용]")
print(f"  pop_modal_cont: {popups.count()}개 (EUM 템플릿. 화면 표시와 무관)")
print(f"  dimmed:         {dimmed.count()}개")

# 3. 실제 가시 팝업 (Playwright is_visible)
print(f"\n[실제 화면에 보이는 팝업 — Playwright is_visible]")
visible_popups = []
for i in range(popups.count()):
    el = popups.nth(i)
    try:
        if el.is_visible(timeout=500):
            cls = el.get_attribute("class") or ""
            txt = el.inner_text(timeout=500)[:80]
            visible_popups.append({"idx": i, "cls": cls, "text": txt})
    except Exception:
        pass

if not visible_popups:
    print("  팝업 없음 (화면이 깨끗한 상태)")
else:
    print(f"  활성 팝업: {len(visible_popups)}개")
    for p in visible_popups:
        print(f"    [{p['idx']}] cls={p['cls'][:50]}")
        print(f"         text={p['text'][:60]}")

# 4. 실제 가시 dimmed
print(f"\n[실제 화면에 보이는 dimmed]")
vd_count = 0
for i in range(dimmed.count()):
    try:
        if dimmed.nth(i).is_visible(timeout=300):
            vd_count += 1
    except Exception:
        pass
print(f"  활성 dimmed: {vd_count}개")

# 5. 결론
print(f"\n[결론]")
if not visible_popups and vd_count == 0 and not popup_windows:
    print("  ✓ 모든 팝업 깨끗 (모달 0개 / 별도 창 0개)")
else:
    if popup_windows:
        print(f"  ⚠  별도 창 팝업 {len(popup_windows)}개 — handle_page_popups()로 처리 필요")
    if visible_popups:
        print(f"  ⚠  모달 팝업 {len(visible_popups)}개 — handle_page_popups()로 처리 필요")
