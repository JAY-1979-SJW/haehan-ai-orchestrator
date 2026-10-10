"""[WEB-AI-PLAYWRIGHT-SIMPLE-FLOW-01] CDP + Playwright smoke test.

검증 항목:
  1. Playwright가 9222 CDP에 연결되는지
  2. /api/v1/cdp/status 가 실제 연결 상태와 일치하는지
  3. 블로그 작성 요청 시 탭 열기(draft 단계)까지 PASS

실제 발행/submit은 하지 않는다.
"""

from __future__ import annotations

import urllib.request

CDP_URL = "http://127.0.0.1:9222"
API_BASE = "http://127.0.0.1:8401"


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _cdp_http_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 - CDP 연결 상태 확인용 테스트 헬퍼 — 예외 시 False(연결 안 됨) 반환 또는 대체 라우터 함수 호출, 읽기 전용 스모크 테스트
        return False


# ── 1. Playwright CDP 연결 ────────────────────────────────────────────────────


def test_playwright_connects_to_cdp():
    """Playwright가 9222 CDP에 연결되고 context·page를 반환한다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL, timeout=5000)
        assert browser.contexts, "context가 없음 — CDP 브라우저에 프로필이 없음"
        pages = browser.contexts[0].pages
        assert len(pages) >= 1, "탭이 0개"


# ── 2. /api/v1/cdp/status 정합성 ─────────────────────────────────────────────


def test_cdp_status_endpoint_matches_reality():
    """/api/v1/cdp/status의 connected 값이 실제 CDP 가용 여부와 일치한다."""
    import json

    actual = _cdp_http_alive()

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # 서버가 실행 중이면 API로 확인, 아니면 라우터 함수 직접 호출
    try:
        with urllib.request.urlopen(f"{API_BASE}/api/v1/cdp/status", timeout=3) as r:
            data = json.loads(r.read())
        api_connected = data.get("connected", False)
    except Exception:  # noqa: BLE001 - CDP 연결 상태 확인용 테스트 헬퍼 — 예외 시 False(연결 안 됨) 반환 또는 대체 라우터 함수 호출, 읽기 전용 스모크 테스트
        # 서버 미실행 시 라우터 함수 직접 호출
        from ai_orchestrator.connectors.cdp_screen_router import _cdp_alive

        api_connected = _cdp_alive()

    assert api_connected == actual, f"API 응답({api_connected})이 실제 CDP 상태({actual})와 불일치"


# ── 3. 블로그 탭 열기 smoke ───────────────────────────────────────────────────


def test_blog_tab_open_smoke():
    """블로그 에디터 URL로 탭을 열고 페이지 제목/URL을 확인한다(draft 단계, 발행 안 함)."""
    from playwright.sync_api import sync_playwright

    BLOG_WRITE_URL = "https://blog.naver.com/write"

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL, timeout=5000)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            page.goto(BLOG_WRITE_URL, wait_until="domcontentloaded", timeout=15000)
            final_url = page.url
            # 로그인 안 된 경우 login 페이지, 된 경우 editor — 둘 다 탭이 열린 것으로 PASS
            assert "naver.com" in final_url, f"예상치 않은 URL: {final_url}"
        finally:
            page.close()
