"""캘린더 페이지 DOM 검사 — 버튼과 팝업 확인"""
from pathlib import Path
import sys
import json
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

port = 9222

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    print("[1] 캘린더 페이지 열기...")
    page.goto("https://calendar.google.com/calendar/u/0/r", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    print("\n[2] 페이지 상태 확인:")
    print(f"  URL: {page.url}")
    print(f"  Title: {page.title}")

    print("\n[3] 버튼 탐색:")
    # 모든 버튼 찾기
    buttons = page.locator("button").all()
    print(f"  총 {len(buttons)}개의 버튼 발견")

    # aria-label이 있는 버튼만 출력
    for i, btn in enumerate(buttons[:30]):
        aria_label = btn.get_attribute("aria-label")
        text = btn.text_content()
        if aria_label or (text and len(text.strip()) > 0):
            print(f"    [{i}] aria-label: {aria_label}, text: {text[:50]}")

    print("\n[4] 특정 선택자 확인:")
    selectors = [
        '[aria-label*="만들기"]',
        '[aria-label*="약속"]',
        '[aria-label*="Create"]',
        'button[aria-label]',
    ]
    for sel in selectors:
        els = page.locator(sel).all()
        print(f"  {sel}: {len(els)}개")
        if els:
            print(f"    첫번째: aria-label = {els[0].get_attribute('aria-label')}")

    print("\n[5] 팝업/모달 확인:")
    # 모달이나 팝업 요소 찾기
    modals = page.locator("role=dialog, [role='dialog']").all()
    print(f"  Dialog 요소: {len(modals)}개")

    overlays = page.locator("[class*='modal'], [class*='popup'], [class*='overlay']").all()
    print(f"  Overlay 요소: {len(overlays)}개")

    print("\n[6] JavaScript로 DOM 구조 확인:")
    dom_info = page.evaluate("""() => {
        const btns = [];
        for (const btn of document.querySelectorAll('button')) {
            btns.push({
                ariaLabel: btn.getAttribute('aria-label'),
                text: btn.textContent.trim().substring(0, 30),
                visible: btn.offsetParent !== null,
                id: btn.id,
                class: btn.className.substring(0, 50)
            });
        }
        return {
            totalButtons: btns.length,
            buttons: btns.slice(0, 15),
            viewportSize: {w: window.innerWidth, h: window.innerHeight},
            bodyClasses: document.body.className.substring(0, 100)
        };
    }""")

    print(f"  뷰포트: {dom_info['viewportSize']}")
    print(f"  Body classes: {dom_info['bodyClasses'][:80]}")
    print(f"  총 버튼: {dom_info['totalButtons']}")
    print("  첫 15개 버튼:")
    for btn in dom_info['buttons']:
        if btn['ariaLabel'] or btn['text']:
            print(f"    - {btn['ariaLabel'] or btn['text'][:40]} (visible: {btn['visible']})")

    page.close()
    print("\n[완료]")
