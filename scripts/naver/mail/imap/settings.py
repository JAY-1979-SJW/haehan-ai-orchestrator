"""네이버 웹메일 "IMAP/SMTP 사용" 설정 읽기·켜기 (CDP 브라우저, 이미 로그인된 세션 사용).

기준서·절차서: docs/specs/2026-10-01_naver_mail_imap_smtp.md
- 화면: https://mail.naver.com/v2/settings/smtp/imap  (환경설정 > POP3/IMAP 설정 > IMAP/SMTP 설정 탭)
- 선택자(2026-10-01 실측): 라디오 `input#option_radio_1` = 사용함 / `#option_radio_2` = 사용 안 함, 저장 `button.button_settings_confirm`,
  저장 뒤 네이버가 "IMAP/SMTP가 사용함으로 설정되었습니다" 확인 창을 띄운다.
- 로그인·로그아웃·쿠키는 건드리지 않는다. 로그인돼 있지 않으면 바꾸지 않고 `not_logged_in` 으로 알린다.
- 화면에 표시된 계정(아이디)이 대상 계정과 다르면 바꾸지 않는다.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

SETTINGS_URL = "https://mail.naver.com/v2/settings/smtp/imap"
ENABLED_RADIO = "input#option_radio_1"
SAVE_BUTTON = "button.button_settings_confirm"
SAVED_NOTICE = "사용함으로 설정되었습니다"
_ACCOUNT_LINE = re.compile(r"아이디\s*:\s*([A-Za-z0-9_.\-]+)")


def _open(page: Any) -> dict[str, Any]:
    """설정 화면을 열고 상태를 읽는다. enabled: True/False, 로그인 안 됐거나 화면을 못 읽으면 None."""
    page.goto(SETTINGS_URL, wait_until="domcontentloaded", timeout=30000)
    if "nid.naver.com" in page.url:
        return {"enabled": None, "account": None, "reason": "not_logged_in"}
    try:
        page.wait_for_selector(ENABLED_RADIO, state="attached", timeout=15000)
    except Exception:  # noqa: BLE001 - 화면 구조가 바뀌었거나 아직 로딩 중: 바꾸지 않고 알린다
        return {"enabled": None, "account": None, "reason": "page_not_ready"}
    match = _ACCOUNT_LINE.search(page.inner_text("body"))
    return {"enabled": bool(page.is_checked(ENABLED_RADIO)), "account": match.group(1) if match else None, "reason": ""}


def read_state(page: Any) -> dict[str, Any]:
    """IMAP/SMTP 사용 설정 상태(읽기 전용)."""
    return _open(page)


def enable(page: Any, account: str) -> dict[str, Any]:
    """ "사용함"으로 바꿔 저장하고, 다시 읽어 반영됐는지 확인한다. 이미 사용함이면 아무것도 바꾸지 않는다."""
    state = _open(page)
    if state["enabled"] is None:
        return {"ok": False, "changed": False, "reason": state["reason"]}
    if state["account"] and state["account"] != account:
        return {"ok": False, "changed": False, "reason": "other_account", "account": state["account"]}
    if state["enabled"]:
        return {"ok": True, "changed": False, "reason": "already_enabled"}

    page.locator(f"label[for='{ENABLED_RADIO.split('#')[1]}']").click(timeout=8000)
    page.locator(SAVE_BUTTON).first.click(timeout=8000)
    with contextlib.suppress(Exception):  # 확인 창이 안 보여도 아래 재확인으로 실제 반영 여부를 판단한다
        page.get_by_text(SAVED_NOTICE).first.wait_for(state="visible", timeout=10000)
    with contextlib.suppress(Exception):  # 확인 창이 이미 닫혔으면 무시
        page.get_by_role("button", name="확인", exact=True).first.click(timeout=3000)

    after = _open(page)  # 새로 불러와 서버에 저장된 값을 확인한다
    if after["enabled"] is True:
        return {"ok": True, "changed": True, "reason": "enabled"}
    return {"ok": False, "changed": True, "reason": "not_saved"}
