"""Gmail CDP 리더 — 이미 로그인된 CDP 세션으로 Gmail 읽기.

OAuth 팝업 없이, CDP 브라우저의 기존 Google 로그인 세션을 재사용한다.
L3 Connectors 계층. 업무 로직 없음.
"""

from __future__ import annotations

import contextlib
import logging

logger = logging.getLogger(__name__)

_GMAIL_INBOX_URL = "https://mail.google.com/mail/u/0/#inbox"


def fetch_gmail_via_cdp(max_results: int = 20) -> list[dict]:
    """CDP 브라우저(기존 Google 세션)로 Gmail 받은편지함을 읽어 반환."""
    from scripts.web_connector import run_on_browser_thread

    def _work():
        from playwright.sync_api import TimeoutError as PWTimeout

        from scripts.web_connector import get_page_by_url, open_page

        # Gmail 탭 찾기 또는 열기
        try:
            page = get_page_by_url("mail.google.com", create_url=_GMAIL_INBOX_URL)
        except Exception:  # noqa: BLE001 - Gmail CDP 탭 조회 실패 시 새 탭을 여는 대체 경로로 폴백(읽기 전용 수집), 메일 목록 조회 실패는 로그 남기고 재raise — 쓰기·발송 없음
            page = open_page(_GMAIL_INBOX_URL)

        # 로딩 대기
        with contextlib.suppress(PWTimeout):
            page.wait_for_load_state("domcontentloaded", timeout=15000)

        # 로그인 여부 확인
        if "accounts.google.com" in page.url or "signin" in page.url:
            raise RuntimeError("Gmail 로그인 필요 — CDP 브라우저에서 Google 계정 로그인 후 재시도")

        # inbox 로 이동 (다른 페이지였으면)
        if "#inbox" not in page.url and "/mail/" not in page.url:
            page.goto(_GMAIL_INBOX_URL, timeout=15000)
            page.wait_for_timeout(2000)

        # 메일 행 추출
        items = page.evaluate(
            """
        (maxResults) => {
            const rows = Array.from(document.querySelectorAll('tr.zA'));
            const result = [];
            for (const row of rows.slice(0, maxResults)) {
                const subjectEl = row.querySelector('.bog span, .y6 span, span.bqe');
                const fromEl = row.querySelector('.yP, .zF, .bA4 span');
                const timeEl = row.querySelector('.xW span, .g3, .xe');
                const snippetEl = row.querySelector('.y2');
                const msgId = row.getAttribute('id') || '';
                result.push({
                    message_id: msgId,
                    from: fromEl ? (fromEl.getAttribute('email') || fromEl.innerText || '').trim() : '',
                    subject: subjectEl ? subjectEl.innerText.trim() : '(no subject)',
                    body_summary: snippetEl ? snippetEl.innerText.trim() : '',
                    received_at: timeEl ? (timeEl.getAttribute('title') || timeEl.innerText || '').trim() : '',
                    body: '',
                });
            }
            return result;
        }
        """,
            max_results,
        )

        return items if isinstance(items, list) else []

    try:
        items = run_on_browser_thread(_work)
        logger.info("Gmail CDP 수집: %d건", len(items))
        return items
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("Gmail CDP 수집 실패: %s", e)
        raise
