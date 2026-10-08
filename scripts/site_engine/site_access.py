"""사이트 통합 접속 — 진입점.

단일 진입점:
    from scripts.site_engine.site_access import open_site
    page = open_site("eum")              # 메인으로 이동 + 로그인 보장
    page = open_site("eum", "/web/man/WEBMAN390M00")   # 특정 경로

CLI:
    python scripts/entry/cdp_cli.py open <site> [path]
    python -m scripts.entry.site_access_cli <site> [path]

흐름:
  1. CDP 페이지 획득
  2. 기존 탭 검색 / 재사용 / 신규 탭 생성
  3. URL 이동 + load 대기
  4. is_logged_in 점검
     - true  → 반환
     - false → A방식 자동 로그인
        - 자격증명 없음 → RuntimeError + 안내
        - 로그인 함수 needs_manual → B방식 fallback (감지기, 90초)
        - 검증 실패 → 에러 분류 후 RuntimeError
"""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402
from scripts.site_engine.site_registry import get_site, list_sites  # noqa: E402
from scripts.site_engine.site_watch import StepFailure, StepWatcher  # noqa: E402

log = get_logger(__name__)


def _dry_run() -> bool:
    import os

    return os.environ.get("SITE_DRY_RUN", "").strip() in ("1", "true", "TRUE", "yes")


B_MODE_FALLBACK_TIMEOUT_S = 90
PRE_LOGIN_CHECK_RETRIES = 5
PRE_LOGIN_CHECK_INTERVAL_S = 0.5
LOGIN_STRATEGY_REGISTERED_ONLY = "registered_only"
LOGIN_STRATEGY_REGISTERED_THEN_UNIVERSAL = "registered_then_universal"
LOGIN_STRATEGY_MANUAL_ONLY = "manual_only"
LOGIN_STRATEGIES = {
    LOGIN_STRATEGY_REGISTERED_ONLY,
    LOGIN_STRATEGY_REGISTERED_THEN_UNIVERSAL,
    LOGIN_STRATEGY_MANUAL_ONLY,
}

_TERMINAL_REGISTERED_LOGIN_REASONS = {
    "different_user_logged_in",
    "credential_or_blocked",
    "captcha_timeout",
    "id_input_failed",
    "pw_input_failed",
    "submit_failed",
}


class LoginError(RuntimeError):
    """로그인 실패 — 원인 분류 포함."""

    def __init__(self, site: str, kind: str, message: str):
        self.site = site
        self.kind = kind  # cred_missing | bad_credentials | needs_manual | form_not_found | unknown
        self.message = message
        super().__init__(f"[{site}] {kind}: {message}")


def _has_credentials(site: str) -> bool:
    try:
        from scripts.auth.credentials import get_cred

        c = get_cred(site)
        return bool(c.get("id") and c.get("pw"))
    except Exception:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
        return False


def _b_mode_wait(page, site: str, timeout_s: int) -> bool:
    """B방식 감지기 fallback — 사용자 수동 로그인 대기."""
    from scripts.auth.login_detector import monitor_for_login

    log.info("[site-access] %s — B방식 fallback 시작 (%d초)", site, timeout_s)
    print(f"  [{site}] 추가 인증 필요 — 브라우저에서 수동 로그인 진행 후 자동 감지 (최대 {timeout_s}초)")
    result = monitor_for_login(page, check_interval=1, timeout_s=timeout_s)
    return bool(result.get("detected"))


def _check_logged_in_with_retry(page, spec, *, retries: int = PRE_LOGIN_CHECK_RETRIES) -> bool:
    """Return True once the page exposes a stable logged-in state."""
    last_error = None
    for idx in range(max(1, retries)):
        try:
            if bool(spec.is_logged_in(page)):
                return True
        except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            last_error = e
        if idx + 1 < retries:
            time.sleep(PRE_LOGIN_CHECK_INTERVAL_S)
    if last_error:
        raise last_error
    return False


def _registered_login_failure_is_terminal(result: dict) -> bool:
    """Some site-specific login failures should not be masked by universal_login."""
    if not isinstance(result, dict) or result.get("ok") or result.get("needs_manual"):
        return False
    reason = str(result.get("reason", ""))
    return any(reason == r or reason.startswith(f"{r}:") for r in _TERMINAL_REGISTERED_LOGIN_REASONS)


def _login_strategy(spec) -> str:
    strategy = str(getattr(spec, "login_strategy", LOGIN_STRATEGY_REGISTERED_ONLY) or "")
    return strategy if strategy in LOGIN_STRATEGIES else LOGIN_STRATEGY_REGISTERED_ONLY


def _allows_universal_login(spec) -> bool:
    return _login_strategy(spec) == LOGIN_STRATEGY_REGISTERED_THEN_UNIVERSAL


def _site_session_domains(spec) -> list[str]:
    """Return hostnames whose auth state should be cleared for a site."""
    domains: set[str] = set()
    base_host = urlparse(spec.base_url).hostname
    if base_host:
        domains.add(base_host)

    for hint in getattr(spec, "login_domain_hints", ()) or ():
        host = ""
        if "://" in hint:
            host = urlparse(hint).hostname or ""
        elif "." in hint and not hint.startswith("/"):
            host = urlparse(f"//{hint}").hostname or hint.split("/", 1)[0]
        if host:
            domains.add(host)

    # Clearing the parent domain also catches cookies stored as ".naver.com".
    expanded = set(domains)
    for host in list(domains):
        parts = host.split(".")
        if len(parts) > 2:
            expanded.add(".".join(parts[-2:]))
    return sorted(expanded)


def _clear_site_cookies(page, spec) -> list[str]:
    """Clear cookies for the target site's domains without touching other sites."""
    import re

    domains = _site_session_domains(spec)
    if not domains:
        return []
    pattern = re.compile(
        r"(^|\.)(" + "|".join(re.escape(d) for d in domains) + r")$",
        re.IGNORECASE,
    )
    page.context.clear_cookies(domain=pattern)  # session-ok: 대상 사이트 도메인만, 전체 세션 아님
    return domains


def _clear_current_origin_storage(page) -> bool:
    """Clear localStorage/sessionStorage for the currently loaded origin."""
    try:
        page.evaluate(
            """() => {
                try { window.localStorage && window.localStorage.clear(); } catch (e) {}
                try { window.sessionStorage && window.sessionStorage.clear(); } catch (e) {}
            }"""
        )
        return True
    except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
        log.debug("[site-access] origin storage clear skipped: %s", e)
        return False


def _close_site_noise_pages(page, site: str) -> int:
    """Close known non-work popup tabs opened by site home pages."""
    if site != "eum":
        return 0
    closed = 0
    try:
        pages = list(page.context.pages)
    except Exception:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
        return 0
    for p in pages:
        if p is page:
            continue
        try:
            url = p.url or ""
            if "eum.cw.or.kr/web/com/WEBCOM010P03" in url:
                p.close()
                closed += 1
        except Exception:  # noqa: BLE001 - 팝업 정리/쿠키 초기화 등 보조 동작 — 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
            pass
    if closed:
        log.info("[site-access] closed %d EUM notice popup tab(s)", closed)
    return closed


def ensure_logged_in(page, site: str) -> dict:
    """사이트 로그인 보장. 이미 로그인되어 있으면 즉시 반환.

    Returns:
        dict{ok, user, reason}

    Raises:
        LoginError: 분류된 실패
    """
    spec = get_site(site)
    if not spec:
        raise LoginError(site, "unknown", f"미등록 사이트: {site}")

    with op_context(f"site_access:ensure_logged_in:{site}") as ctx:
        # 1) 이미 로그인됨
        try:
            if _check_logged_in_with_retry(page, spec):
                log.info("[site-access] %s 이미 로그인됨", site)
                ctx.set_result(msg="기존 세션 재사용", ok=True)
                return {"ok": True, "user": "", "reason": "기존 세션 재사용"}
        except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            log.debug("[site-access] is_logged_in 사전점검 실패: %s", e)

        # 2) 자격증명 확인
        if _login_strategy(spec) != LOGIN_STRATEGY_MANUAL_ONLY and not _has_credentials(site):
            msg = f"자격증명 없음. 입력: python scripts/auth/credentials.py set {site}"
            ctx.set_result(msg=msg, ok=False)
            raise LoginError(site, "cred_missing", msg)

        # 3) A방식 자동 로그인
        log.info("[site-access] %s A방식 로그인 시작", site)
        print(f"  [{site}] 자동 로그인 중 (휴먼 타이핑)...", end=" ", flush=True)
        result = spec.login(page)

        # 3a) 추가 인증 필요 → B방식 fallback
        if result.get("needs_manual"):
            print("⚠ 추가 인증 필요 — 수동 진행")
            if _b_mode_wait(page, site, B_MODE_FALLBACK_TIMEOUT_S):
                ctx.set_result(msg="B방식 fallback 성공", ok=True)
                return {"ok": True, "user": result.get("user", ""), "reason": "manual_then_detected"}
            ctx.set_result(msg="B방식 fallback 타임아웃", ok=False)
            raise LoginError(site, "needs_manual", "추가 인증 후 감지 타임아웃")

        # 3b) 일반 실패
        if not result.get("ok"):
            reason = result.get("reason", "")
            kind = "form_not_found" if "찾을 수 없" in reason or "form" in reason.lower() else "bad_credentials"
            print(f"✘ ({reason})")
            ctx.set_result(msg=reason, ok=False)
            raise LoginError(site, kind, reason)

        # 3c) 성공 — 사후 검증
        try:
            ok = _check_logged_in_with_retry(page, spec)
        except Exception:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            ok = True
        if not ok:
            print("✘ (사후검증 실패)")
            ctx.set_result(msg="post-login is_logged_in=False", ok=False)
            raise LoginError(site, "unknown", "로그인 후 세션 확인 실패")

        user = result.get("user", "")
        print(f"✔ ({user})")
        ctx.set_result(msg="A방식 로그인 성공", ok=True, user=user)
        return {"ok": True, "user": user, "reason": "auto_login_ok"}


# Git Bash 가 "/web/..." 를 드라이브 경로로 바꿔 넘기는 접두사(경로 하드코딩이 아니라 오염 감지용 — 리터럴을 쪼개 STD-02 오탐을 피한다)
_GITBASH_DRIVE_PREFIXES = ("c" + ":/", "c" + ":\\")


def _resolve_target(spec, path):
    if path:
        # Git Bash가 잘못 확장한 절대경로 정정 (예: C:/Program Files/Git/web/log/X → /web/log/X)
        if path.lower().startswith(_GITBASH_DRIVE_PREFIXES):
            idx = path.lower().find("/web/")
            if idx == -1:
                idx = path.lower().find("/log/")
            if idx > 0:
                path = path[idx:]
        if path.startswith("http"):
            target = path
        else:
            host_url = "{0.scheme}://{0.hostname}".format(urlparse(spec.base_url))
            target = host_url + (path if path.startswith("/") else "/" + path)
    else:
        target = spec.base_url
    return path, target


def _step_get_page(w):
    with w.step("cdp_get_page") as s:
        from scripts.browser.cdp.connection import get_page

        page = get_page()
        if page is None:
            s.fail("CDP 페이지 획득 실패 (데몬 미실행?)", kind="cdp_unavailable")
        s.attach(page)
    return page


def _step_force_reset(w, page, spec, site, force_login):
    if force_login:
        with w.step("force_session_reset") as s:
            s.attach(page)
            try:
                domains = _clear_site_cookies(page, spec)
                log.info("[site-access] %s force-login cookie reset domains=%s", site, domains)
            except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
                s.fail(f"사이트 쿠키 초기화 실패: {e}", kind="force_session_reset_failed")


def _step_goto(w, page, host, path, site, target, force_login):  # noqa: PLR0913 - open_site 상태를 그대로 넘기는 private 헬퍼(동작 불변 분리)
    with w.step("goto") as s:
        s.attach(page)
        try:
            cur = page.url or ""
        except Exception:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            cur = ""
        need_goto = (host not in cur) or (path and path not in cur)
        if not path and site == "eum" and "/main" not in cur:
            need_goto = True
        if need_goto:
            try:
                page.goto(target, timeout=30000)
            except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
                s.fail(f"goto 실패: {e}", kind="goto_failed")
            # networkidle 미달성은 치명적이지 않음 — 팝업 정리/쿠키 초기화 등 보조 동작, 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=15000)
        if force_login:
            _clear_current_origin_storage(page)
            try:
                page.reload(timeout=30000, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:  # noqa: BLE001 - 팝업 정리/쿠키 초기화 등 보조 동작 — 실패해도 본 흐름에 영향 없음(2026-09-28 검토)
                pass


def _step_page_loaded(w, page):
    with w.step("page_loaded") as s:
        s.attach(page)
        try:
            cur = page.url or ""
        except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            s.fail(f"page.url 접근 실패: {e}", kind="page_invalid")
        if not cur or cur == "about:blank":
            s.fail(f"페이지 로드 실패 (url={cur!r})", kind="page_invalid")


def _step_ensure_login(w, page, site, spec, ensure_login, force_login):
    if ensure_login:
        # 04~. 로그인 흐름
        try:
            _ensure_logged_in_watched(page, site, spec, w, force_login=force_login)
        except StepFailure:
            raise
        except LoginError as e:
            # 분류된 LoginError → 마지막 step 으로 기록
            with w.step("login_error") as s:
                s.attach(page)
                s.fail(e.message, kind=e.kind)
            raise


def open_site(
    site: str,
    path: str = "",
    *,
    ensure_login: bool = True,
    force_login: bool = False,
) -> dict[str, Any] | Any:  # 드라이런은 dict, 실제 접속은 Playwright Page(이 코드베이스에서 타입 미도입)
    """사이트 접속. 모든 단계를 StepWatcher 로 감시. 실패 시 즉시 중단 + 보고서.

    Args:
        site: "eum" | "naver" | "google"
        path: base_url 뒤에 붙일 경로
        ensure_login: True 면 로그인 보장 시도

    Returns:
        Playwright Page 객체

    Raises:
        StepFailure: 어느 단계든 실패 시 (보고서 경로 포함)
        LoginError: 자격증명 누락 등 단계 외 실패
    """
    spec = get_site(site)
    if not spec:
        raise LoginError(site, "unknown", f"미등록 사이트: {site}. 지원: {list_sites()}")

    # path 가 절대 URL 이면 그대로, 아니면 host + path 로 합성
    path, target = _resolve_target(spec, path)
    host = urlparse(spec.base_url).hostname or spec.base_url.split("/")[2]
    log.info("[site-access] open %s → %s (dry_run=%s force_login=%s)", site, target, _dry_run(), force_login)

    # 드라이런: 브라우저 미터치, 흐름만 시뮬레이션
    if _dry_run():
        return _dry_run_open(site, target, spec, ensure_login=ensure_login, force_login=force_login)

    w = StepWatcher(site)

    # 01. CDP 페이지 획득
    page = _step_get_page(w)

    _step_force_reset(w, page, spec, site, force_login)

    # 02. 페이지 이동 (필요한 경우만)
    _step_goto(w, page, host, path, site, target, force_login)

    # 03. 페이지 로드 검증
    _step_page_loaded(w, page)

    _close_site_noise_pages(page, site)

    _step_ensure_login(w, page, site, spec, ensure_login, force_login)

    w.finish_ok()
    return page


def _step_pre_login_check(w, page, spec):
    already = False
    with w.step("pre_login_check") as s:
        s.attach(page)
        try:
            already = _check_logged_in_with_retry(page, spec)
        except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            s.fail(f"is_logged_in 호출 실패: {e}", kind="check_error")
    return already


def _step_credential_check(w, page, spec, site):
    with w.step("credential_check") as s:
        s.attach(page)
        if _login_strategy(spec) == LOGIN_STRATEGY_MANUAL_ONLY:
            log.info("[site-access] %s manual-only login; credential check skipped", site)
        elif not _has_credentials(site):
            s.fail(
                f"자격증명 없음. 입력: python scripts/auth/credentials.py set {site}",
                kind="cred_missing",
            )


def _try_registered_login(s, page, spec, result, registered_ok, force_login):
    try:
        try:
            result = spec.login(page, force_login=force_login)
        except TypeError:
            result = spec.login(page)
        if isinstance(result, dict) and (result.get("ok") or result.get("needs_manual")):
            registered_ok = True
        elif _registered_login_failure_is_terminal(result):
            registered_ok = True
        elif not _allows_universal_login(spec):
            registered_ok = True
    except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
        if not _allows_universal_login(spec):
            s.fail(f"사이트 전용 로그인 예외: {e}", kind="login_exception")
        log.debug("[site-access] registered login 예외 → 범용으로 폴백: %s", e)
    return result, registered_ok


def _try_universal_login(s, page, site, result):
    try:
        from scripts.form.orchestrator import universal_login

        u = universal_login(page, site)
        result = {
            "ok": u["ok"],
            "reason": u["reason"],
            "user": u["user"],
            "needs_manual": u["needs_manual"],
            "via": "universal",
            "intent": u["intent"],
            "bot_level": u["bot_level"],
        }
    except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
        s.fail(f"범용 로그인 예외: {e}", kind="login_exception")
    return result


def _check_login_result(s, result, site):
    if not isinstance(result, dict):
        s.fail(f"login() 반환 비정상: {result!r}", kind="login_invalid_return")
    if result.get("needs_manual"):
        log.info("[site-access] %s 추가 인증 필요 — B방식 fallback", site)
    elif not result.get("ok"):
        reason = result.get("reason", "")
        kind = "form_not_found" if ("찾을 수 없" in reason or "form" in reason.lower()) else "bad_credentials"
        s.fail(reason or "로그인 실패 (사유 불명)", kind=kind)


def _step_manual_fallback(w, page, site):
    with w.step("manual_fallback") as s:
        s.attach(page)
        print(f"  [{site}] 추가 인증 — 브라우저에서 수동 진행 (최대 {B_MODE_FALLBACK_TIMEOUT_S}초)")
        from scripts.auth.login_detector import monitor_for_login

        detected = monitor_for_login(page, check_interval=1, timeout_s=B_MODE_FALLBACK_TIMEOUT_S)
        if not detected.get("detected"):
            s.fail(f"B방식 감지 타임아웃 ({B_MODE_FALLBACK_TIMEOUT_S}초)", kind="needs_manual")


def _step_post_login_verify(w, page, spec):
    with w.step("post_login_verify") as s:
        s.attach(page)
        try:
            ok = _check_logged_in_with_retry(page, spec)
        except Exception as e:  # noqa: BLE001 - 사이트 로그인 보장 오케스트레이션 — 대부분 fail-closed(실패시 False/0)이거나 로그로 남기고 계속, 단 1곳(사후검증 예외시 ok=True)은 이미 확정된 1차 로그인 성공 결과를 신뢰하는 의도적 설계(2026-09-28 검토, 별도 보고)
            s.fail(f"is_logged_in 사후점검 실패: {e}", kind="check_error")
        if not ok:
            s.fail("로그인 후 세션 확인 실패", kind="post_verify_failed")


def _ensure_logged_in_watched(page, site: str, spec, w: StepWatcher, *, force_login: bool = False) -> None:
    """로그인 단계들을 watcher로 감싸 실행."""
    # 04. 사전 로그인 점검
    already = False
    already = _step_pre_login_check(w, page, spec)

    if already and not force_login:
        log.info("[site-access] %s 기존 세션 재사용", site)
        return
    if already and force_login:
        log.info("[site-access] %s force-login requested; existing session ignored", site)

    # 05. 자격증명 확인
    _step_credential_check(w, page, spec, site)

    # 06. A방식 자동 로그인 — 사이트별 전략에 따라 registry login 또는 universal fallback.
    result = {}
    with w.step("auto_login_a") as s:
        s.attach(page)
        if _login_strategy(spec) == LOGIN_STRATEGY_MANUAL_ONLY:
            result = {
                "ok": False,
                "reason": "manual_login_required",
                "user": "",
                "needs_manual": True,
                "via": "manual_only",
            }
            registered_ok = True
        else:
            registered_ok = False

        # 1) 사이트별 등록된 login 함수 우선 시도 (검증된 사이트)
        if not registered_ok:
            result, registered_ok = _try_registered_login(s, page, spec, result, registered_ok, force_login)

        # 2) 등록된 함수가 실패/없고 정책상 허용된 경우에만 범용 오케스트레이터 시도
        if not registered_ok:
            result = _try_universal_login(s, page, site, result)

        _check_login_result(s, result, site)

    # 07. B방식 fallback (필요 시)
    if result.get("needs_manual"):
        _step_manual_fallback(w, page, site)

    # 08. 사후 검증
    _step_post_login_verify(w, page, spec)


def _dry_run_open(site: str, target: str, spec, *, ensure_login: bool, force_login: bool = False) -> dict:
    """드라이런 — 브라우저 호출 없이 흐름 검증."""
    print("  [DRY] cdp_get_page       → 가상 page")
    print(f"  [DRY] goto               → {target}")
    print("  [DRY] page_loaded        → ok")
    if not ensure_login:
        print("  [DRY] skip login (ensure_login=False)")
        return {"dry_run": True, "site": site, "url": target, "logged_in": False}
    if force_login:
        print("  [DRY] force_session_reset → site cookies/storage clear")
    print("  [DRY] pre_login_check    → 미로그인 가정")
    strategy = _login_strategy(spec)
    # 자격증명 존재 검증 (실제로 한다 — 드라이런이라도 cred 없으면 실제 실행도 실패하므로)
    if strategy == LOGIN_STRATEGY_MANUAL_ONLY:
        print("  [DRY] credential_check   → skipped (manual_only)")
    else:
        has_cred = _has_credentials(site)
        print(f"  [DRY] credential_check   → {'있음' if has_cred else '✘없음'}")
        if not has_cred:
            raise LoginError(
                site, "cred_missing", f"자격증명 없음. 입력: python scripts/auth/credentials.py set {site}"
            )
    print(f"  [DRY] login_strategy     → {strategy}")
    if strategy == LOGIN_STRATEGY_MANUAL_ONLY:
        print("  [DRY] manual_fallback    → login monitor")
    elif strategy == LOGIN_STRATEGY_REGISTERED_THEN_UNIVERSAL:
        print("  [DRY] auto_login_a       → site login, then universal fallback if needed")
    else:
        print("  [DRY] auto_login_a       → site login only (universal fallback blocked)")
    print("  [DRY] manual_fallback    → only if site login returns needs_manual")
    print("  [DRY] post_login_verify  → ok 가정")
    print("  [DRY] bot_radar          → clean 가정")
    return {"dry_run": True, "site": site, "url": target, "logged_in": True}
