"""네이버 ID/PW 자동 로그인 모듈.

네이버는 자동화 봇 감지가 강하므로:
  - 사람처럼 천천히 타이핑
  - 캡차/2차인증 감지 시 사용자에게 위임
  - 보안문자 등장 시 즉시 중단 + 사용자 알림

자격증명 우선순위:
  1. 함수 파라미터 (id, pw)
  2. 환경변수 (NAVER_ID, NAVER_PW)
  3. .env 파일 (data/.env_naver)

사용:
  from scripts.naver.common.auth import login_naver
  from scripts.browser.cdp.connection import get_page

  page = get_page()
  result = login_naver(page)  # 환경변수/파일 사용
  # 또는: login_naver(page, naver_id="...", naver_pw="...")
  # 결과: {ok, user, reason}
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Any

from scripts.auth.login_detector import detect_login_state, wait_for_login_generic
from scripts.browser.page.human_input import safe_human_input
from scripts.browser.popup.popup_detector import handle_page_popups
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from ai_orchestrator.core.security_utils import mask_identifier

_log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / "data" / ".env_naver"

NAVER_LOGIN_URL = "https://www.naver.com/"


# ── 자격증명 로드 ──────────────────────────────────────────────────────────


def _load_from_cred_store(nid: str | None, pw: str | None) -> tuple[str | None, str | None]:
    """통합 저장소(암호화)에서 ID/PW 보충."""
    if not pw:
        try:
            from scripts.auth.credentials import get_cred

            if nid:
                cred = get_cred(f"naver:{nid}")
                # 명시된 계정에 pw 없으면 기본 계정으로 폴백하지 않음
            else:
                cred = get_cred("naver")
                if not nid and cred.get("id"):
                    nid = cred["id"]
            if not pw and cred.get("pw"):
                pw = cred["pw"]
        except Exception as e:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
            _log.debug("통합 자격증명 로드 실패: %s", e)
    return nid, pw


def _load_from_legacy_file(nid: str | None, pw: str | None) -> tuple[str | None, str | None]:
    """레거시 평문 파일에서 ID/PW 보충."""
    if (not nid or not pw) and ENV_FILE.exists():
        _log.warning(
            "[naver-auth] 평문 자격증명 파일을 사용 중 — `python scripts/auth/credentials.py migrate` 로 암호화 저장소로 이전하세요"
        )
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "NAVER_ID" and not nid:
                    nid = v
                elif k == "NAVER_PW" and not pw:
                    pw = v
        except Exception as e:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
            _log.debug("자격증명 파일 읽기 실패: %s", e)
    return nid, pw


def _load_credentials(
    naver_id: str | None = None,
    naver_pw: str | None = None,
) -> tuple[str | None, str | None]:
    """ID/PW 조회. 파라미터 → 통합 저장소(credentials.json, 암호화) → 환경변수 → 레거시 파일."""
    nid = naver_id
    pw = naver_pw

    # 1. 통합 저장소 (암호화) — 계정별 "naver:ID" 키 우선, 없으면 기본 "naver"
    # 단, nid가 명시된 경우 기본 "naver" 계정으로 폴백하지 않음 (다른 계정 PW 혼용 방지)
    nid, pw = _load_from_cred_store(nid, pw)

    # 2. 환경변수
    if not nid:
        nid = os.environ.get("NAVER_ID")
    if not pw:
        pw = os.environ.get("NAVER_PW")

    # 3. 레거시 평문 파일 (백업 경로) — 폐지 예정. 값은 로그에 남기지 않는다.
    nid, pw = _load_from_legacy_file(nid, pw)

    return nid, pw


def save_credentials(naver_id: str, naver_pw: str) -> Path:
    """네이버 자격증명을 통합 암호화 저장소(scripts.auth.credentials)에 저장한다.

    예전에는 data/.env_naver 에 평문으로 썼으나(2026-09-30 폐지), 이제 계정별 키 "naver:<id>" 로
    암호화 저장한다. 기본 계정 "naver" 가 아직 없으면 같은 값을 기본으로도 둔다.
    반환값은 하위 호환을 위해 저장소 파일 경로다. 비밀번호는 로그에 남기지 않는다.
    """
    from scripts.auth.credentials import CRED_FILE, get_cred, set_cred

    set_cred(f"naver:{naver_id}", id=naver_id, pw=naver_pw)
    if not get_cred("naver").get("id"):
        set_cred("naver", id=naver_id, pw=naver_pw)
    _log.info("[naver-auth] 자격증명 저장(암호화): naver:%s", mask_identifier(naver_id))
    return CRED_FILE


# ── 봇 감지 회피 타이핑 + 안전 입력 ────────────────────────────────────────


# 입력 칸 클릭 대기 시간. 2초는 PC 가 느릴 때(메모리 부족·다른 작업 부하) 네이버 로그인 폼의 안정화·페이지 이동 대기를
# 못 기다려 아이디/비밀번호 칸 클릭이 번갈아 시간 초과됐다(2026-09-30 실측). 실패해도 제출 전이라 안전하므로 넉넉히 둔다.
_INPUT_CLICK_TIMEOUT_MS = 8000


def _redact_input_result(result: dict) -> dict:
    """Remove raw credential values from a safe_human_input result."""
    redacted = dict(result)
    for key in ("before", "after"):
        if key in redacted:
            value = str(redacted.get(key) or "")
            redacted[f"{key}_len"] = len(value)
            redacted[key] = "[REDACTED]" if value else ""
    return redacted


# ── 캡차/보안문자 감지 ─────────────────────────────────────────────────────


def _submit_login_form(page) -> dict:
    """Submit the login form with fallbacks for unstable animated buttons."""
    selector = '.btn_login, #log\\.login, button[type="submit"]'
    try:
        page.locator(selector).first.click(timeout=3000)
        return {"ok": True, "method": "click"}
    except Exception as click_error:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        _log.warning("[naver-auth] login button normal click failed: %s", str(click_error)[:120])

    try:
        clicked = page.evaluate(
            """() => {
                const btn = document.querySelector('.btn_login, #log\\\\.login, button[type="submit"]');
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if clicked:
            return {"ok": True, "method": "js_click"}
    except Exception as js_error:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        _log.warning("[naver-auth] login button js click failed: %s", str(js_error)[:120])

    try:
        page.locator("#pw").press("Enter", timeout=2000)
        return {"ok": True, "method": "enter"}
    except Exception as enter_error:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        return {"ok": False, "reason": str(enter_error)[:120]}


def _open_login_from_naver_main(page) -> dict:
    """Start Naver login — 직접 로그인 폼 URL 이동 (실검증 2026-06-23).

    www.naver.com 경유 클릭 방식은 MyView 리뉴얼로 불안정 → mode=form URL 직접 이동.
    """
    # 이미 로그인 폼에 있으면 바로 반환
    try:
        if page.locator("#id").first.is_visible(timeout=1000):
            return {"ok": True, "method": "already_on_login_form"}
    except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
        pass

    # 직접 로그인 폼 이동 (가장 안정적)
    page.goto(
        "https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/",
        timeout=15000,
        wait_until="domcontentloaded",
    )
    time.sleep(1.0)
    try:
        page.locator("#id").first.wait_for(state="visible", timeout=8000)
        return {"ok": True, "method": "direct_form_url"}
    except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
        pass

    # fallback: www.naver.com 경유 클릭 (리뉴얼 UI)
    page.goto(NAVER_LOGIN_URL, timeout=15000, wait_until="domcontentloaded")
    time.sleep(1.0)
    selectors = (
        "a.MyView-module__link_login___HpHMW",
        "[class*='link_login']",
        "a[href*='nidlogin.login?mode=form']",
        "a[href*='nid.naver.com/nidlogin.login']",
    )
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if not el.is_visible(timeout=1000):
                continue
            el.click(timeout=3000)
            page.locator("#id").first.wait_for(state="visible", timeout=10000)
            return {"ok": True, "method": f"click:{selector}"}
        except Exception:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
            continue

    return {"ok": False, "reason": "login_link_not_found"}


def _detect_captcha(page) -> bool:
    """캡차/보안문자/2차인증 감지."""
    try:
        return page.evaluate("""
        (() => {
            const txt = (document.body?.innerText || '').toLowerCase();
            if (/캡차|보안문자|captcha|2단계|2차\\s*인증|otp|일회용/i.test(txt)) return true;
            // 이미지 input
            if (document.querySelector('img[id*="captcha"], img[src*="captcha"]')) return true;
            return false;
        })();
        """)
    except Exception:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        return False


# ── 메인 로그인 함수 ────────────────────────────────────────────────────────


def _existing_login_verdict(page, nid: str, force_relogin: bool) -> dict[str, Any] | None:
    """이미 로그인돼 있을 때의 결과. 로그인이 안 돼 있거나 판정에 실패하면 None(로그인 절차로 진행).

    사용자명을 모르면(요소 기준 판정은 화면에 이름이 없으면 None) "다른 사용자"라고 단정하지 않고
    `logged_in_account_unknown` 으로 알린다 — 올바르게 로그인된 세션을 다른 사용자로 오판하지 않기 위해(2026-10-01).
    """
    try:
        state = detect_login_state(page)
        if not state.get("logged_in") or "naver" not in page.url or force_relogin:
            return None
        current_user = state.get("user") or ""
    except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
        return None
    if (current_user and nid in current_user) or current_user == nid:
        _log.info("[naver-auth] 동일 사용자 이미 로그인됨: %s", current_user)
        return {"ok": True, "user": current_user, "reason": "already_logged_in"}
    if not current_user:
        _log.info("[naver-auth] 이미 로그인됨 — 화면에서 사용자명을 알 수 없음 (목표: %s)", nid)
        return {
            "ok": False,
            "reason": "logged_in_account_unknown",
            "target_user": nid,
            "hint": "이미 로그인돼 있으나 어느 계정인지 화면에서 확인할 수 없음. 계정 확인 후 필요하면 직접 로그아웃.",
        }
    _log.warning("[naver-auth] 다른 사용자 로그인 상태: %s (목표: %s)", current_user, nid)
    return {
        "ok": False,
        "reason": "different_user_logged_in",
        "current_user": current_user,
        "target_user": nid,
        "hint": "현재 다른 사용자로 로그인됨. 먼저 로그아웃 필요.",
    }


def _wait_for_user_challenge(page, nid: str, wait_for_user_s: int) -> dict[str, Any]:
    """캡차·2차인증이 떴을 때: 자동으로 넘기지 않고 사용자가 브라우저에서 처리할 때까지 기다린다."""
    _log.warning("[naver-auth] 캡차/2차인증 감지 → 사용자 수동 처리 대기")
    log_critical("AUTH_FAIL", "네이버 로그인 캡차/2차인증", user=nid, mode="captcha_detected")
    state = wait_for_login_generic(page, max_wait_s=wait_for_user_s, poll_interval=3.0)
    if state.get("logged_in"):
        user = state.get("user") or nid
        log_critical("AUTH_SUCCESS", "네이버 로그인 성공 (사용자 처리)", user=user, mode="auto_login_done_manual")
        return {"ok": True, "user": user, "reason": "user_handled_captcha"}
    return {"ok": False, "reason": "captcha_timeout", "captcha_required": True, "needs_manual": True}


def _fill_login_form(page, nid: str, pw: str) -> dict[str, Any] | None:
    """아이디·비밀번호 칸 입력(브라우저 자동 채우기 값은 지우고 다시 입력). 성공이면 None, 실패면 오류 결과."""
    id_result = safe_human_input(page, "#id", nid, label="ID", delay_ms=70, click_timeout_ms=_INPUT_CLICK_TIMEOUT_MS)
    if not id_result["ok"]:
        _log.error("[naver-auth] ID 입력 실패: %s", id_result.get("reason"))
        return {"ok": False, "reason": f"id_input_failed:{id_result.get('reason', 'unknown')}", "id_result": id_result}
    time.sleep(0.6)

    pw_result = safe_human_input(page, "#pw", pw, label="PW", delay_ms=80, click_timeout_ms=_INPUT_CLICK_TIMEOUT_MS)
    if not pw_result["ok"]:
        _log.error("[naver-auth] PW 입력 실패: %s", pw_result.get("reason"))
        return {
            "ok": False,
            "reason": f"pw_input_failed:{pw_result.get('reason', 'unknown')}",
            "pw_result": _redact_input_result(pw_result),
        }
    time.sleep(0.5)

    _log.info("[naver-auth] 입력 완료 — ID:%s, PW:%s", id_result["action"], pw_result["action"])
    return None


def login_naver(
    page,
    naver_id: str | None = None,
    naver_pw: str | None = None,
    wait_for_user_s: int = 300,
    force_relogin: bool = False,
) -> dict[str, Any]:
    """네이버 ID/PW 로그인.

    Args:
        page: Playwright Page
        naver_id: 네이버 ID (없으면 환경변수/파일 조회)
        naver_pw: 네이버 PW (동일)
        wait_for_user_s: 캡차 등 발생 시 사용자 수동 처리 대기 시간

    Returns:
        {ok, user, reason, captcha_required}
    """
    # 1. 자격증명
    nid, pw = _load_credentials(naver_id, naver_pw)
    if not nid or not pw:
        return {
            "ok": False,
            "reason": "no_credentials",
            "hint": "환경변수 NAVER_ID/NAVER_PW 또는 data/.env_naver 파일 필요",
        }

    log_critical("AUTH_SUCCESS", "네이버 로그인 시도", user=nid, mode="auto_login_start")

    # 2. 이미 로그인 상태 확인 (같은 사용자 / 다른 사용자 / 사용자 불명)
    existing = _existing_login_verdict(page, nid, force_relogin)
    if existing is not None:
        return existing

    # 3. 로그인 페이지 진입
    _log.info("[naver-auth] 로그인 페이지 진입")
    entry_result = _open_login_from_naver_main(page)
    if not entry_result.get("ok"):
        return {
            "ok": False,
            "reason": f"login_entry_failed:{entry_result.get('reason', 'unknown')}",
            "needs_manual": True,
            "current_url": page.url,
        }
    time.sleep(1)

    # 4. ID/PW 입력 — 안전 입력 (기존 자동완성 값 처리)
    input_failure = _fill_login_form(page, nid, pw)
    if input_failure is not None:
        return input_failure

    # 5. 로그인 버튼 클릭
    try:
        submit_result = _submit_login_form(page)
        if not submit_result.get("ok"):
            raise RuntimeError(submit_result.get("reason", "submit_failed"))
        time.sleep(3)
    except Exception as e:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        _log.error("[naver-auth] 로그인 버튼 클릭 실패: %s", e)
        return {"ok": False, "reason": f"submit_failed:{str(e)[:60]}"}

    # 6. 캡차/2차인증 감지
    if _detect_captcha(page):
        return _wait_for_user_challenge(page, nid, wait_for_user_s)

    # 7. 일반 성공 검증
    time.sleep(2)
    state = detect_login_state(page)
    if state.get("logged_in"):
        user = state.get("user") or nid
        _log.info("[naver-auth] 로그인 성공: %s", user)
        log_critical("AUTH_SUCCESS", "네이버 로그인 성공", user=user, mode="auto_login_done")
        return {"ok": True, "user": user, "reason": "ok"}

    # 8. 실패
    # URL이 여전히 로그인 페이지면 실패
    if "nidlogin" in page.url or "login" in page.url:
        log_critical("AUTH_FAIL", "네이버 로그인 실패", user=nid, mode="auto_login_fail")
        return {"ok": False, "reason": "credential_or_blocked", "current_url": page.url, "needs_manual": True}

    # 9. 점수 낮아도 다른 페이지로 이동했으면 일단 ok
    return {"ok": state.get("score", 0) >= 2, "user": state.get("user"), "reason": "ambiguous"}


def _get_actual_naver_id(page) -> str:
    """현재 로그인된 네이버 실제 ID 반환 (닉네임이 아닌 ID).

    네이버 내정보 API에서 loginId를 추출. 실패 시 빈 문자열.
    """
    try:
        resp = page.evaluate("""
            fetch('https://nid.naver.com/user2/api/page/nmain', {credentials:'include'})
              .then(r => r.text()).catch(() => '')
        """)
        m = __import__("re").search(r'"loginId"\s*:\s*"([^"]+)"', resp or "")
        if m:
            return m.group(1)
        # 쿠키 기반 fallback: 블로그 접근 URL에서 ID 추출
        cur = page.url
        page.goto("https://blog.naver.com/MyBlog.naver", wait_until="domcontentloaded", timeout=8000)
        import time as _t

        _t.sleep(1)
        redirected = page.url  # https://blog.naver.com/{id}
        page.goto(cur, wait_until="domcontentloaded", timeout=8000)
        m2 = __import__("re").search(r"blog\.naver\.com/([^/?#]+)", redirected)
        if m2 and m2.group(1) not in ("", "MyBlog.naver"):
            return m2.group(1)
    except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
        pass
    return ""


def _naver_auth_cookies_present(page) -> bool:
    """네이버 인증 쿠키(NID_AUT + NID_SES)가 컨텍스트에 있으면 True.

    httpOnly 라 페이지 JS(document.cookie)로는 안 보이므로 Playwright 컨텍스트에서 직접 조회.
    """
    try:
        cookies = page.context.cookies("https://www.naver.com")
        names = {c.get("name") for c in cookies}
        return "NID_AUT" in names and "NID_SES" in names
    except Exception:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        return False


def _ensure_on_naver_domain(page) -> None:
    """현재 페이지가 네이버 도메인이 아니면 네이버로 이동."""
    # 현재 페이지가 네이버 도메인이 아니면 로그인 판정 전에 네이버로 이동
    # (호출처가 about:blank/타 사이트에 있어도 쿠키 기반 로그인을 올바로 감지하기 위함)
    try:
        _cur = page.url or ""
    except Exception:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        _cur = ""
    if "naver.com" not in _cur:
        try:
            page.goto("https://www.naver.com/", timeout=20000, wait_until="domcontentloaded")
            time.sleep(1)
        except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
            pass


def _handle_logged_in_state(page, state: dict, naver_id: str | None, naver_pw: str | None) -> dict[str, Any] | None:
    """이미 로그인된 상태 처리(계정 전환 필요 시 재로그인). 로그인 상태가 아니면 None."""
    current_user = (state.get("user") or "").strip().lower()
    target_user = (naver_id or "").strip().lower()

    if state.get("logged_in"):
        # 이미 로그인됐는데 다른 계정이 요청된 경우 → 재로그인 필요
        # user는 닉네임일 수 있으므로 blog URL 접근으로 실제 ID 확인
        if target_user and current_user and current_user != target_user:
            actual_id = _get_actual_naver_id(page) or current_user
            if actual_id.lower() == target_user:
                return {"ok": True, "user": actual_id, "reason": "already_logged_in"}
            _log.info("[naver-auth] 계정 전환 필요: %s → %s", actual_id, target_user)
            # pw 자동 탐색 (naver:{id} 키 우선)
            if not naver_pw:
                try:
                    from scripts.auth.credentials import get_naver_cred

                    cred = get_naver_cred(naver_id or "")
                    naver_pw = cred.get("pw", "")
                except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
                    pass
            if naver_pw:
                return login_naver(page, naver_id=naver_id, naver_pw=naver_pw, force_relogin=True)
            return {"ok": False, "reason": f"{naver_id} 비밀번호를 찾을 수 없습니다"}
        return {"ok": True, "user": state.get("user"), "reason": "already_logged_in"}
    return None


def _fill_naver_pw(naver_id: str | None, naver_pw: str | None) -> str | None:
    """pw 미전달 시 자격증명 자동 탐색."""
    if naver_id and not naver_pw:
        try:
            from scripts.auth.credentials import get_naver_cred

            cred = get_naver_cred(naver_id)
            naver_pw = cred.get("pw", "")
        except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
            pass
    return naver_pw


def _try_auth_window_gate(page) -> dict[str, Any] | None:
    """순차 인증창 게이트(SSO 우선). 결과를 확정할 수 있으면 dict, 아니면 None."""
    try:
        from scripts.naver.common.auth_window_gate import (
            STAGE_CAPTCHA,
            STAGE_LOGGED_IN,
            STAGE_TWO_FACTOR,
            advance_once,
        )

        step = advance_once(page)
        if step.get("action") == "sso_clicked":
            time.sleep(5)
            step = advance_once(page)
            if step.get("action") == "wait_callback":
                time.sleep(4)
                step = advance_once(page)
        if step.get("stage") == STAGE_LOGGED_IN and detect_login_state(page).get("logged_in"):
            ls = detect_login_state(page)
            return {"ok": True, "user": ls.get("user"), "reason": "sso_logged_in"}
        if step.get("stage") in (STAGE_TWO_FACTOR, STAGE_CAPTCHA):
            reason = "two_factor_required" if step["stage"] == STAGE_TWO_FACTOR else "captcha_required"
            _log.warning("[naver-auth] 인증창 게이트: %s → 사용자 입력 대기", reason)
            return {
                "ok": False,
                "reason": reason,
                "needs_user": True,
                "hint": step.get("hint"),
                "captcha_required": step["stage"] == STAGE_CAPTCHA,
            }
    except Exception as e:  # noqa: BLE001 - 네이버 로그인 자동화 — 실패 시 항상 {ok: False, reason} 구조로 상위에 알리거나 안전한 기본값(False/빈문자열)으로 폴백(fail-closed), 자격증명 값은 로그에 남기지 않음, 로그인 우회·세션 위조 없음(2026-09-28 검토)
        _log.debug("[naver-auth] auth-gate 스킵: %s", str(e)[:100])
    return None


def ensure_naver_login(
    page,
    naver_id: str | None = None,
    naver_pw: str | None = None,
    return_url: str | None = None,
) -> dict[str, Any]:
    """현재 페이지의 네이버 도메인 로그인 확인 → 미로그인이면 자동 로그인 → 원래 페이지 복귀."""
    _ensure_on_naver_domain(page)

    state = detect_login_state(page)
    handled = _handle_logged_in_state(page, state, naver_id, naver_pw)
    if handled is not None:
        return handled

    # 폴백: 범용 JS 감지 실패해도 네이버 인증 쿠키(NID_AUT+NID_SES)가 있으면 로그인으로 인정.
    # 이 쿠키는 httpOnly 라 detect_login_state 의 document.cookie 신호로는 안 잡힌다.
    if _naver_auth_cookies_present(page):
        _log.info("[naver-auth] JS 감지 실패했으나 네이버 인증 쿠키 확인 → 로그인 인정")
        return {"ok": True, "user": state.get("user"), "reason": "naver_cookie"}

    # pw 미전달 시 자격증명 자동 탐색
    naver_pw = _fill_naver_pw(naver_id, naver_pw)

    original_url = return_url or page.url

    # ── 순차 인증창 게이트 (SSO 우선) ──────────────────────────────────────────
    # 네이버 세션이 있으면 커머스 SSO(간편 로그인)를 자동 클릭한다. 그 결과 2단계 인증(2FA)·
    # 캡차가 뜨면 자동 입력이 불가능한 보안 단계이므로 명확한 사유로 반환(섹션 실패로 묻히지 않게).
    gate_result = _try_auth_window_gate(page)
    if gate_result is not None:
        return gate_result

    # ── fallback: 기존 자격증명 기반 로그인 ────────────────────────────────────
    result = login_naver(page, naver_id, naver_pw)
    if not result["ok"]:
        return result

    # 원래 페이지 복귀
    if original_url and "nidlogin" not in original_url:
        try:
            page.goto(original_url, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2)
        except Exception:  # noqa: BLE001 - 여러 로그인 폼 진입 경로를 순차 시도하는 best-effort — 하나 실패해도 다음 방법 또는 상위 fallback으로 계속(2026-09-28 검토)
            pass
    return result


def open_logged_in_page(page, url: str) -> bool:
    """네이버 로그인 확인 후 url 로 이동하고 팝업을 정리한다. 로그인 실패면 False.

    mybox/talk/calendar/place 의 Naver*.open 이 URL 만 다르게 똑같이 복사해 쓰던 본문을 한 곳으로 모았다.
    """
    result = ensure_naver_login(page, return_url=url)
    if not result.get("ok"):
        return False
    page.goto(url, timeout=20000, wait_until="domcontentloaded")
    time.sleep(3)
    # 팝업 처리 시도 실패는 무시하고 계속 진행 — 진입 직후 팝업이 남아도 이후 조회·작업 로직이 각자 처리
    with contextlib.suppress(Exception):
        handle_page_popups(page, timeout_s=1.5)
    return True
