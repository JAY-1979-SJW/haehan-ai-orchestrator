"""CDP로 인스타그램(big.sun2024)에 캐러셀 게시물 발행.

실측 확인된 UI 흐름(2026-08-19):
1. https://www.instagram.com/create/select/ 직접 진입 → input[type=file] 즉시 존재
2. set_input_files로 이미지 여러 장(캐러셀) 업로드 — 네이티브 파일선택창 없이 바로 됨
3. '다음' 버튼 클릭(자르기/필터 단계) → 캡션 화면(textarea[aria-label="문구를 입력하세요..."])
4. 캡션 채우고, confirmed=True 일 때만 실제 '공유하기' 클릭

주의: 이 페이지에서 page.screenshot()은 폰트로딩 대기에서 타임아웃되는 경우가
잦음(2026-08-19 실측) — 상태 확인은 screenshot 대신 evaluate()/inner_text()로 한다.
"""

from __future__ import annotations

from scripts.instagram.caption import build_caption
from scripts.instagram.cases import Case, mark_posted
from scripts.common.logger import get_logger

_log = get_logger(__name__)

CDP_URL = "http://127.0.0.1:9222"
CREATE_URL = "https://www.instagram.com/create/select/"
CAPTION_SELECTOR = 'textarea[aria-label="문구를 입력하세요..."]'


def _get_page(ctx):
    for p in ctx.pages:
        if "instagram.com" in p.url:
            return p
    return ctx.new_page()


def publish_case(case: Case, confirmed: bool = False, approval: str | None = None) -> dict:
    """case의 이미지를 업로드하고 캡션을 채운다. confirmed=True + 승인 문구(approval)가 있을 때만 실제 게시."""
    from playwright.sync_api import sync_playwright

    if confirmed:  # 브라우저를 열기 전에 확인한다
        from scripts.common.gate import require_approved

        require_approved("instagram_publish", approval, via="ig_publish_case", case_id=case.case_id)

    caption = build_caption(case)
    result = {"case_id": case.case_id, "image_count": len(case.images), "caption": caption, "posted": False}

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = _get_page(ctx)
        page.goto(CREATE_URL, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        finput = page.locator("input[type=file]").first
        finput.set_input_files([str(p) for p in case.images])
        page.wait_for_timeout(2500)
        _log.info(f"[ig-publish] 이미지 {len(case.images)}장 업로드: {case.case_id}")

        page.get_by_text("다음", exact=True).first.click(timeout=10000)
        page.wait_for_timeout(1500)
        # 필터 단계가 있으면 한 번 더 '다음'
        try:
            page.get_by_text("다음", exact=True).first.click(timeout=4000)
            page.wait_for_timeout(1500)
        except Exception:  # noqa: BLE001 - 인스타그램 게시 브라우저 자동화 - 버튼 클릭 best-effort, 실패해도 다음 단계(캡션 입력)로 계속 진행
            pass

        ta = page.locator(CAPTION_SELECTOR)
        ta.click(timeout=10000)
        ta.fill(caption)
        page.wait_for_timeout(500)

        if not confirmed:
            _log.info("[ig-publish] confirmed=False — 업로드/캡션까지만, 실제 발행 안 함")
            return result

        page.get_by_text("공유하기", exact=True).first.click(timeout=10000)
        page.wait_for_timeout(4000)
        result["posted"] = True
        mark_posted(case)
        _log.info(f"[ig-publish] 발행 완료: {case.case_id}")

    return result
