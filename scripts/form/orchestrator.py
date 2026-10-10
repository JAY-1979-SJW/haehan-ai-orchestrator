"""범용 로그인 오케스트레이터 — 어떤 사이트든 동작.

공용 유틸 의존:
  - form.discovery   : 폼 자동 탐색 + 의미 매핑
  - form.profile     : 개인정보 (사이트 override)
  - form.human       : 휴먼 타이핑 (베지어 마우스 + 사고 일시정지)
  - form.events      : 이벤트 기반 대기 (blind sleep 없음)
  - form.bot_radar   : 봇 감지 매 단계
  - credentials      : 통합 자격증명 (Fernet 암호화)

사용:
    from scripts.form.orchestrator import universal_login
    r = universal_login(page, site="eum")
    # r: {ok, user, reason, intent, fields_used}

라우터에 호스트별 site_key 매핑이 없어도 동작 (discovery 기반).
site 인자는 자격증명/프로필 키로만 사용.
"""

from __future__ import annotations

import contextlib
from typing import Any

from scripts.form.bot_radar import scan as bot_scan
from scripts.form.discovery import discover_form
from scripts.form.events import wait_for_form, wait_submit_done, wait_validation
from scripts.form.human import human_click, human_type
from scripts.common.logger import get_logger

log = get_logger(__name__)


# 로그인 성공/실패 시그널 (대부분의 사이트 공통)
_SUCCESS_DOM_HINTS = [
    "a:has-text('로그아웃')",
    "button:has-text('로그아웃')",
    "[onclick*='logout']",
    "[href*='logout']",
    "[id='btnLogout']",
    "[class*='btn-logout']",
]

_FAIL_TEXT_HINTS = [
    "비밀번호가 일치하지 않",
    "아이디 또는 비밀번호",
    "잘못된 아이디",
    "존재하지 않는 회원",
    "incorrect password",
    "invalid credentials",
    "wrong password",
    "user not found",
    "로그인 정보가 올바르지 않",
]

_FAIL_SELECTORS = [
    ".error",
    ".err",
    ".warning",
    ".alert-danger",
    "[role='alert']",
    "[class*='error-msg']",
    "[class*='login-error']",
]


def _resolve_credentials(site: str) -> tuple[str, str]:
    """site 키로 ID/PW 조회. 통합 credentials → profile override 순."""
    # 1) credentials.json
    try:
        from scripts.auth.credentials import get_cred

        c = get_cred(site)
        if c.get("id") and c.get("pw"):
            return c["id"], c["pw"]
    except Exception as e:  # noqa: BLE001 - 폼 자동 로그인 오케스트레이터 - 자격증명 조회/제출 실패는 debug 로그(값 노출 없음) 후 다음 방식으로 폴백하거나 실패 사유를 반환
        log.debug("[orchestrator] credentials 조회 실패: %s", e)

    # 2) profile (site override → base)
    try:
        from scripts.form.personal_profile import get_value

        nid = get_value("default_id", site=site)
        pw = get_value("default_pw", site=site)
        if nid and pw:
            return nid, pw
    except Exception as e:  # noqa: BLE001 - 폼 자동 로그인 오케스트레이터 - 자격증명 조회/제출 실패는 debug 로그(값 노출 없음) 후 다음 방식으로 폴백하거나 실패 사유를 반환
        log.debug("[orchestrator] profile 조회 실패: %s", e)

    return "", ""


def _warn_inline_validation(page, selector: str) -> None:
    """ID 입력 직후 인라인 검증 메시지(예: "사용자가 없습니다")가 있으면 경고 로그."""
    vmsg = wait_validation(page, selector, timeout_ms=600)
    if vmsg.get("found"):
        msg = vmsg.get("message", "").lower()
        if any(s in msg for s in ["없", "확인", "invalid", "not found", "잘못"]):
            log.warning("[orchestrator] ID 인라인 검증 경고: %s", vmsg["message"])


def _submit_login(page, disc, pw_field, result: dict) -> bool:
    """로그인 제출 — submit 버튼 우선, 없거나 실패하면 Enter. 제출 오류 시 result["reason"] 설정 후 False."""
    if disc.submit_selector:
        r_sub = human_click(page, disc.submit_selector, label="로그인 버튼")
        if not r_sub.get("ok"):
            # 버튼 클릭 실패 → Enter 폴백
            try:
                page.locator(pw_field.selector).press("Enter")
            except Exception as e:  # noqa: BLE001 - 폼 자동 로그인 오케스트레이터 - 자격증명 조회/제출 실패는 debug 로그(값 노출 없음) 후 다음 방식으로 폴백하거나 실패 사유를 반환
                result["reason"] = f"제출 실패: {e}"
                return False
    else:
        try:
            page.locator(pw_field.selector).press("Enter")
        except Exception as e:  # noqa: BLE001 - 폼 자동 로그인 오케스트레이터 - 자격증명 조회/제출 실패는 debug 로그(값 노출 없음) 후 다음 방식으로 폴백하거나 실패 사유를 반환
            result["reason"] = f"제출 실패(Enter): {e}"
            return False
    return True


def _judge_login_result(page, done: dict, nid: str, wait_submit_ms: int, result: dict) -> None:
    """제출 응답(done)으로 로그인 성공/실패를 판정해 result 에 기록."""
    kind = done.get("kind")
    detail = done.get("detail", "")

    if kind in ("fail_dom", "fail_text"):
        result["reason"] = f"로그인 실패: {detail[:200]}"
        return

    if kind == "success_dom" or kind == "url_changed":
        result["ok"] = True
        result["user"] = nid
        result["reason"] = f"로그인 성공 ({kind})"
        return

    if kind == "timeout":
        # 마지막 보루: 로그인 폼이 사라졌으면 성공으로 간주
        try:
            disc2 = discover_form(page)
            has_pw = any(f.role == "password" for f in disc2.fields)
            if not has_pw:
                result["ok"] = True
                result["user"] = nid
                result["reason"] = "로그인 성공 (폼 사라짐)"
                return
        except Exception:  # noqa: BLE001 - 폼 자동 로그인 오케스트레이터 - 자격증명 조회/제출 실패는 debug 로그(값 노출 없음) 후 다음 방식으로 폴백하거나 실패 사유를 반환
            pass
        result["reason"] = f"응답 타임아웃 ({wait_submit_ms}ms)"
        return

    result["reason"] = f"판정 불가 ({kind}: {detail[:120]})"


def universal_login(page, site: str, *, wait_form_ms: int = 8000, wait_submit_ms: int = 12000) -> dict:
    """범용 로그인. 사이트별 selector 없이 discovery로 폼 찾고 휴먼 타이핑.

    Args:
        page: Playwright Page (이미 로그인 페이지/메인에 있어야 함)
        site: 자격증명 키 (eum, naver, google, ...)
        wait_form_ms: SPA 폼 등장 대기 (필요 시)
        wait_submit_ms: 제출 응답 대기

    Returns:
        dict{
            ok: bool,
            user: str,
            reason: str,
            intent: str,           # discovery로 추정한 페이지 intent
            fields_used: [role,...],
            bot_level: str,
            needs_manual: bool,    # CAPTCHA/2FA 감지 시 True
        }
    """
    result: dict[str, Any] = {
        "ok": False,
        "user": "",
        "reason": "",
        "intent": "unknown",
        "fields_used": [],
        "bot_level": "clean",
        "needs_manual": False,
    }

    # 1) 자격증명 조회
    nid, pw = _resolve_credentials(site)
    if not nid or not pw:
        result["reason"] = f"자격증명 없음. 입력: python scripts/auth/credentials.py set {site}"
        return result

    # 2) 폼 대기 (SPA 대응)
    wait_for_form(page, role_hints=["id", "user", "login", "password", "email"], timeout_ms=wait_form_ms)

    # 3) 봇 사전 스캔
    pre = bot_scan(page)
    result["bot_level"] = pre["level"]
    if pre["flagged"]:
        result["reason"] = f"진입 시점 봇 감지: level={pre['level']} vendors={pre['vendors']}"
        result["needs_manual"] = True
        return result

    # 4) 폼 자동 탐색
    disc = discover_form(page)
    result["intent"] = disc.intent

    id_field = disc.get("id") or disc.get("email")
    pw_field = disc.get("password")

    if not id_field or not pw_field:
        result["reason"] = (
            f"로그인 폼 탐지 실패 (id={id_field is not None}, pw={pw_field is not None}, "
            f"intent={disc.intent}, fields={len(disc.fields)})"
        )
        return result

    log.info(
        "[orchestrator] 폼 탐지 — id sel=%s score=%.2f / pw sel=%s score=%.2f",
        id_field.selector,
        id_field.score,
        pw_field.selector,
        pw_field.score,
    )

    before_url = ""
    with contextlib.suppress(Exception):
        before_url = page.url or ""

    # 5) ID 입력 (휴먼 타이핑)
    r_id = human_type(page, id_field.selector, nid, label="ID")
    if not r_id.get("ok"):
        result["reason"] = f"ID 입력 실패: {r_id.get('reason', '')}"
        return result
    result["fields_used"].append("id")

    # 즉시 인라인 검증 메시지 체크 (예: "사용자가 없습니다")
    _warn_inline_validation(page, id_field.selector)

    # 6) PW 입력
    r_pw = human_type(page, pw_field.selector, pw, label="PW", simulate_typo=False)
    if not r_pw.get("ok"):
        result["reason"] = f"PW 입력 실패: {r_pw.get('reason', '')}"
        return result
    result["fields_used"].append("password")

    # 7) 입력 직후 봇 스캔 (CAPTCHA 등장 가능)
    mid = bot_scan(page)
    result["bot_level"] = mid["level"]
    if mid["flagged"]:
        result["reason"] = f"입력 후 봇 감지: {mid['level']} vendors={mid['vendors']}"
        result["needs_manual"] = True
        return result

    # 8) 제출 — submit 버튼 우선, 없으면 Enter
    if not _submit_login(page, disc, pw_field, result):
        return result

    # 9) 응답 대기 — URL 변경 / 성공 DOM / 실패 DOM / 실패 텍스트 중 first
    done = wait_submit_done(
        page,
        before_url=before_url,
        timeout_ms=wait_submit_ms,
        success_selectors=_SUCCESS_DOM_HINTS,
        fail_selectors=_FAIL_SELECTORS,
        fail_signals=_FAIL_TEXT_HINTS,
    )

    # 10) 사후 봇 스캔
    post = bot_scan(page)
    result["bot_level"] = post["level"]
    if post["flagged"]:
        result["reason"] = f"제출 후 봇 감지: {post['level']} vendors={post['vendors']}"
        result["needs_manual"] = True
        return result

    # 11) 결과 판정
    _judge_login_result(page, done, nid, wait_submit_ms, result)
    return result
