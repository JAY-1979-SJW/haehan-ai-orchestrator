"""Gmail CDP 리더 — 이미 로그인된 CDP 세션으로 Gmail 읽기.

OAuth 팝업 없이, CDP 브라우저의 기존 Google 로그인 세션을 재사용한다.
L3 Connectors 계층. 업무 로직 없음.
"""

from __future__ import annotations

import contextlib
import logging
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_GMAIL_INBOX_URL = "https://mail.google.com/mail/u/0/#inbox"


def fetch_gmail_via_cdp(max_results: int = 20) -> list[dict]:
    """CDP 브라우저(기존 Google 세션)로 Gmail 받은편지함을 읽어 반환."""
    from scripts.browser.cdp.connection import run_on_browser_thread

    def _work():
        from playwright.sync_api import TimeoutError as PWTimeout

        from scripts.browser.page.web_connector import get_page_by_url
        from scripts.browser.cdp.connection import open_page

        # Gmail 탭 찾기 또는 열기
        try:
            page = get_page_by_url("mail.google.com", create_url=_GMAIL_INBOX_URL)
        except Exception as exc:  # noqa: BLE001 - Gmail CDP 탭 조회 실패 시 새 탭을 여는 대체 경로로 폴백(읽기 전용 수집), 메일 목록 조회 실패는 로그 남기고 재raise — 쓰기·발송 없음
            logger.warning("Gmail CDP 탭 조회(새 탭 폴백) 실패: %s", type(exc).__name__)
            # 2026-09-29 수정: open_page() 는 키워드 전용 인자만 받는다(*, allow_new_tab,
            # reason) — URL을 여는 파라미터 자체가 없다. 이 폴백 경로는 여태 한 번도
            # 실행된 적이 없어(위 try가 항상 성공) 잠복해 있던 버그였고, 공유 CDP 연결이
            # 일시적으로 불안정했던 상황에서 처음 실행되며 발견됨(TypeError: open_page()
            # takes 0 positional arguments but 1 was given). 새 탭을 열고 직접 이동하도록 수정.
            page = open_page(allow_new_tab=True, reason="gmail-cdp-fallback")
            page.goto(_GMAIL_INBOX_URL, timeout=30000)

        # 로딩 대기
        with contextlib.suppress(PWTimeout):
            page.wait_for_load_state("domcontentloaded", timeout=15000)

        # 로그인 여부 확인. 호스트 기반(실제 accounts.google.com 리다이렉트만 감지) —
        # Gmail 자체 URL의 flowName=GlifWebSignIn 같은 진입 파라미터는 로그인 성공 후에도
        # 주소창에 남아있을 수 있어(SPA가 URL을 갱신 안 함) URL 문자열 검사는 신뢰 불가로
        # 확인됨(2026-09-29 실측: 로그인 완료·받은편지함 50건 표시 상태에서도 URL에
        # "GlifWebSignIn" 잔존). 호스트 + DOM(로그인 폼 잔존 여부) 이중 확인으로 대체.
        host = urlsplit(page.url).hostname or ""
        if host != "mail.google.com":
            raise RuntimeError("Gmail 로그인 필요 — CDP 브라우저에서 Google 계정 로그인 후 재시도")
        still_signin = page.evaluate("!!document.querySelector('input[type=\"email\"], #identifierId, #accountList')")
        if still_signin:
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
