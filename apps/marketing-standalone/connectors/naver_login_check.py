"""네이버 로그인 상태 확인 — 독립 앱 전용 (자동 로그인/비밀번호 저장 없음).

원본(scripts/naver/common/auth.py::ensure_naver_login)은 회사 계정 여러 개를 자동
전환하기 위해 scripts.auth.credentials(암호화 저장된 비밀번호)로 자동 재로그인까지
한다. 이 독립 앱은 **고객의 네이버 비밀번호를 절대 저장하지 않는다**는 설계
원칙이라(setup_gui.py의 "네이버 로그인 열기" 버튼으로 고객이 직접 로그인),
자동 로그인 로직 자체를 포팅하지 않는다 — 로그인 여부만 확인하고, 안 됐으면
사용자에게 직접 로그인하라고 안내한다.
"""

from __future__ import annotations

import sys as _sys
import time
from pathlib import Path as _Path

_APP_ROOT = _Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_APP_ROOT))
from _bootstrap import get_logger  # noqa: E402

_log = get_logger(__name__)


def _naver_auth_cookies_present(page) -> bool:
    """네이버 인증 쿠키(NID_AUT + NID_SES) 존재 여부. httpOnly라 JS로는 안 보여 Playwright 컨텍스트에서 직접 조회."""
    try:
        cookies = page.context.cookies("https://www.naver.com")
        names = {c.get("name") for c in cookies}
        return "NID_AUT" in names and "NID_SES" in names
    except Exception:  # noqa: BLE001 - 네이버 로그인 상태 읽기전용 확인(쿠키 존재 여부·현재 URL 조회) — 실패 시 False/빈문자열로 안전하게 폴백, 로그인 세션을 바꾸거나 파기하지 않음
        return False


def check_login(page) -> dict:
    """현재 세션이 네이버에 로그인돼있는지 확인. 자동 로그인 시도 없음(fail로 안내만)."""
    try:
        cur = page.url or ""
    except Exception:  # noqa: BLE001 - 네이버 로그인 상태 읽기전용 확인(쿠키 존재 여부·현재 URL 조회) — 실패 시 False/빈문자열로 안전하게 폴백, 로그인 세션을 바꾸거나 파기하지 않음
        cur = ""
    if "naver.com" not in cur:
        try:
            page.goto("https://www.naver.com/", timeout=20000, wait_until="domcontentloaded")
            time.sleep(1)
        except Exception as e:  # noqa: BLE001 - 네이버 로그인 상태 읽기전용 확인(쿠키 존재 여부·현재 URL 조회) — 실패 시 False/빈문자열로 안전하게 폴백, 로그인 세션을 바꾸거나 파기하지 않음
            _log.debug("naver.com 이동 실패(무시, 쿠키 확인은 계속): %s", e)

    if _naver_auth_cookies_present(page):
        return {"ok": True, "reason": "naver_cookie"}

    return {
        "ok": False,
        "reason": "manual_login_required",
        "hint": "네이버 로그인이 필요합니다 — setup_gui.py의 '네이버 로그인 열기' 버튼으로 직접 로그인해주세요.",
    }
