"""하나팩스(www.hanafax.com) 인증 모듈.

자격증명 저장:
    python scripts/entry/cdp_cli.py cred set hanafax

사용:
    from scripts.hanafax.auth import get_credentials, test_login
"""

from __future__ import annotations

from scripts.common.logger import get_logger

log = get_logger(__name__)

HANAFAX_BASE = "https://www.hanafax.com"


def get_credentials() -> tuple[str, str]:
    """저장된 하나팩스 자격증명 반환. (user_id, password)"""
    from scripts.auth.credentials import get_cred

    cred = get_cred("hanafax")
    return cred.get("id", ""), cred.get("pw", "")


def test_login(user_id: str | None = None, password: str | None = None) -> dict:
    """로그인 테스트 (팩스 전송 없음). 잔액/팩스번호 정보 반환."""
    uid, pwd = user_id or "", password or ""
    if not uid or not pwd:
        uid, pwd = get_credentials()
    if not uid or not pwd:
        return {"ok": False, "message": "자격증명 없음. python scripts/entry/cdp_cli.py cred set hanafax"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "message": "playwright 미설치. pip install playwright && playwright install chromium"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()
        page.on("dialog", lambda d: d.accept())
        try:
            page.goto(HANAFAX_BASE, wait_until="domcontentloaded", timeout=15_000)
            page.fill('input[name="struid"]', uid)
            page.fill('input[name="strpwd"]', pwd)
            page.evaluate("document.querySelector('form').submit()")
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
            page.wait_for_timeout(1_500)

            cookies = context.cookies()
            if not any(c["name"] == "Login" for c in cookies):
                return {"ok": False, "message": "로그인 실패 (Login 쿠키 없음)"}

            info = page.evaluate("() => document.body.innerText.substring(0, 600)")
            log.info("[hanafax] 로그인 성공: %s", page.url)
            return {"ok": True, "message": "로그인 성공", "url": page.url, "info": info}
        except Exception as e:  # noqa: BLE001 - 하나팩스 로그인 자동화 - 로그인 성공 여부 확인 후 실패 시 ok:False로 반환(fail-closed), 크리덴셜 원문은 로그/반환값에 노출하지 않음
            return {"ok": False, "message": str(e)}
        finally:
            browser.close()
