"""KAKAO-DEV-3R — 전용 프로필 기반 Kakao 앱 목록 관찰.

전용 프로필(kakao_developer_console)을 사용해 Kakao Developers 앱 목록을 관찰한다.
- READY_LOGGED_IN: 앱 목록/앱 설정 메뉴 관찰 진행
- NEEDS_REAUTH + interactive_login=False: pending task 생성 후 종료
- NEEDS_REAUTH + interactive_login=True: 브라우저 유지, 로그인 완료 감지 후 관찰 진행
  - 60초 남았을 때 경고 출력
  - timeout 시 NEEDS_REAUTH_TIMEOUT 기록

절대 금지:
  - 비밀번호/OTP 자동 입력
  - password input value 읽기
  - 쿠키/session/storage_state 추출
  - API key / Client Secret 원문 저장
  - 앱 삭제 / Secret 재발급·폐기
  - 실제 권한 신청 제출
  - push
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time as _time_default
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PROFILE_NAME = "kakao_developer_console"
_CONSOLE_NAME = "kakao_developers"
_TARGET_URL = "https://developers.kakao.com/console/app"
_SESSION_HEALTH_SCRIPT = Path(__file__).resolve().parent / "check_developer_console_sessions.py"

_SECRET_PATTERN = re.compile(
    r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}",
    re.IGNORECASE,
)

_LOGIN_TOKENS = (
    "로그인", "sign in", "signin", "login", "카카오 계정",
    "이메일 또는 전화번호", "비밀번호",
)
_AUTH_TOKENS = (
    "로그아웃", "logout", "내 애플리케이션", "앱 목록", "대시보드",
    "마이앱", "my app",
)
_APP_LIST_TOKENS = (
    "내 애플리케이션", "앱 목록", "애플리케이션 목록", "앱 이름",
    "앱 만들기", "application",
)
_KAKAO_LOGIN_MENU_TOKENS = ("카카오 로그인", "kakao login")
_CONSENT_MENU_TOKENS = ("동의항목", "consent", "개인정보 동의")
_BIZ_APP_TOKENS = ("비즈앱", "비즈니스 앱", "biz app")
_KAKAO_SYNC_TOKENS = ("카카오싱크", "kakao sync")
_REDIRECT_URI_TOKENS = ("redirect uri", "redirect_uri", "리다이렉트")
_PLATFORM_TOKENS = ("플랫폼", "platform", "도메인 등록", "web platform")
_PERMISSION_TOKENS = ("권한 신청", "추가 기능", "비즈니스 권한", "business", "permission request")

# Success signals for login completion detection
_SUCCESS_URL_TOKENS = ["/console/app"]
_SUCCESS_TEXT_TOKENS = ["내 애플리케이션", "앱 목록", "로그아웃"]

_LOGIN_COMPLETE_PROMPT = (
    "\n[observe_kakao_apps] 로그인이 완료되었으면 Enter, 아직 아니면 n + Enter: "
)
_BROWSER_CLOSE_PROMPT = (
    "\n[observe_kakao_apps] 관찰 완료. Enter를 눌러 브라우저를 닫으세요: "
)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(t.lower() in lower for t in tokens)


def _mask_secrets(text: str) -> str:
    return _SECRET_PATTERN.sub("[MASKED]", text)


def _has_secret_like(text: str) -> bool:
    return bool(_SECRET_PATTERN.search(text))


def _check_session_health() -> str:
    """session health check 스크립트를 실행해 kakao_developers 상태를 반환."""
    try:
        result = subprocess.run(
            [sys.executable, str(_SESSION_HEALTH_SCRIPT), "--json"],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(result.stdout)
        for console in data.get("consoles", []):
            if console.get("console") == _CONSOLE_NAME:
                return console.get("status", "UNKNOWN")
    except Exception:
        pass
    return "UNKNOWN"


def _create_pending_task(run_dir: Path, session_status: str) -> Path:
    task = {
        "task_key": "KAKAO-DEV-3R-REAUTH",
        "title": "kakao_developer_console 세션 갱신 후 앱 목록 재관찰",
        "status": "PENDING",
        "session_status": session_status,
        "profile_name": _PROFILE_NAME,
        "target_url": _TARGET_URL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resume_script": "scripts/observe_kakao_apps.py",
        "resume_command": "python scripts/observe_kakao_apps.py --interactive-login --json",
        "auto_executable": False,
        "auth_principal_required": "developer_console_operator",
        "notes": "세션 갱신(로그인) 후 --interactive-login 옵션으로 재실행",
    }
    path = run_dir / "pending_task.json"
    path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _sanitize(raw: dict) -> dict:
    safe: dict[str, Any] = {}
    for k in ("success", "error_code", "warnings", "page_state",
               "title", "status_code", "text_length",
               "links_count", "buttons_count", "screenshot_path"):
        if k in raw:
            safe[k] = raw[k]

    text = raw.get("text_excerpt", "") or ""
    if _has_secret_like(text):
        safe["text_excerpt"] = _mask_secrets(text[:500])
        safe["secret_like_detected"] = True
    else:
        safe["text_excerpt"] = text[:500]
        safe["secret_like_detected"] = False

    safe["links"] = [{"text": lnk.get("text", "")[:80]}
                     for lnk in (raw.get("links") or [])[:20]]
    safe["buttons"] = [{"text": btn.get("text", "")[:80]}
                       for btn in (raw.get("buttons") or [])[:20]]
    return safe


def _extract_signals(raw: dict) -> dict[str, bool]:
    text = (raw.get("text_excerpt") or "").lower()
    title = (raw.get("title") or "").lower()
    links = " ".join(lnk.get("text", "") for lnk in (raw.get("links") or []))
    buttons = " ".join(btn.get("text", "") for btn in (raw.get("buttons") or []))
    combined = text + " " + title + " " + links + " " + buttons
    return {
        "apps_visible": _contains_any(combined, _APP_LIST_TOKENS),
        "kakao_login_menu_found": _contains_any(combined, _KAKAO_LOGIN_MENU_TOKENS),
        "consent_items_menu_found": _contains_any(combined, _CONSENT_MENU_TOKENS),
        "business_app_menu_found": _contains_any(combined, _BIZ_APP_TOKENS),
        "kakao_sync_menu_found": _contains_any(combined, _KAKAO_SYNC_TOKENS),
        "redirect_uri_menu_found": _contains_any(combined, _REDIRECT_URI_TOKENS),
        "platform_menu_found": _contains_any(combined, _PLATFORM_TOKENS),
        "permission_request_menu_found": _contains_any(combined, _PERMISSION_TOKENS),
    }


def _classify_login_state(raw: dict) -> str:
    text = (raw.get("text_excerpt") or "").lower()
    title = (raw.get("title") or "").lower()
    combined = text + " " + title
    if _contains_any(combined, _AUTH_TOKENS):
        return "READY_LOGGED_IN"
    if _contains_any(combined, _LOGIN_TOKENS):
        return "NEEDS_REAUTH"
    return "UNKNOWN"


def _build_next_actions(session_status: str, signals: dict) -> list[dict]:
    actions: list[dict] = []
    if session_status in ("NEEDS_REAUTH", "NEEDS_REAUTH_TIMEOUT", "UNKNOWN"):
        actions.append({
            "task_key": "KAKAO-DEV-3R-REAUTH",
            "title": "developer_console_operator 세션 갱신 후 재관찰",
            "auto_executable": False,
            "auth_principal_required": "developer_console_operator",
            "risk_level": "LOW",
            "approval_required": False,
        })
    if session_status == "READY_LOGGED_IN" or signals.get("apps_visible"):
        actions.append({
            "task_key": "KAKAO-DEV-4",
            "title": "앱 설정 상세 관찰 (platform, redirect URI, login 활성화)",
            "auto_executable": True,
            "auth_principal_required": None,
            "risk_level": "LOW",
            "approval_required": False,
        })
    actions.append({
        "task_key": "KAKAO-OAUTH-1",
        "title": "Kakao OAuth local callback/token flow 설계",
        "auto_executable": True,
        "auth_principal_required": None,
        "risk_level": "LOW",
        "approval_required": False,
    })
    return actions


# ── interactive login wait ─────────────────────────────────────────────────

def _is_strong_login_signal(reasons: list[str]) -> bool:
    """url_changed 단독, success_url_match 단독은 strong reason이 아니다.

    url_changed + 다른 신호가 있어야 완료 처리한다.
    로그인 페이지 → 앱 목록 리다이렉트만으로는 완료로 오판정하지 않도록 한다.
    """
    non_url_and_non_success = [
        r for r in reasons
        if r != "url_changed" and not r.startswith("success_url_match:")
    ]
    # url_changed 단독이면 False
    if not non_url_and_non_success:
        return False
    # user_confirmed_login은 항상 strong
    if "user_confirmed_login" in reasons:
        return True
    # 명확한 로그인 완료 신호
    strong_signals = {"password_input_disappeared", "login_required_hint_cleared"}
    for r in reasons:
        if r in strong_signals or r.startswith("success_text_match:"):
            return True
    return False


def _has_post_login_signal(current: dict, initial: dict) -> bool:
    """URL 변경만으로는 완료 처리하지 않는다. post-login signal이 있어야 한다."""
    from local_agent.browser_login_probe import _detect_completion
    reasons = _detect_completion(
        initial=initial, current=current,
        success_urls=_SUCCESS_URL_TOKENS,
        success_texts=_SUCCESS_TEXT_TOKENS,
    )
    return _is_strong_login_signal(reasons)


def _is_interactive_stdin() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _interactive_wait(
    login_timeout_seconds: int = 300,
    poll_interval_seconds: int = 5,
    extend_on_activity: bool = True,
    max_extensions: int = 3,
    *,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _clock: Any = None,
    _input_reader: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """브라우저를 열고 로그인 완료까지 대기한다.

    - browser.close()는 로그인 대기 완료 후에만 호출한다.
    - URL 변경만으로 완료 처리하지 않는다. post-login signal 필요.
    - 60초 남았을 때 경고를 출력한다.
    - timeout 시 NEEDS_REAUTH_TIMEOUT을 반환한다.
    - ID/PW 자동 입력, password value 읽기, cookie/session export 금지.
    """
    from local_agent.browser_login_probe import _observe, _detect_completion
    from local_agent.browser_reader import _safe_close

    time_mod = _clock or _time_default
    # _input_reader 주입 시 대화형으로 간주 (테스트 포함)
    # 미주입 시 실제 stdin isatty()로 판정
    interactive_mode = (_input_reader is not None) or _is_interactive_stdin()
    input_fn = _input_reader if _input_reader is not None else input

    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright
            factory = sync_playwright
        except ImportError:
            return {
                "session_status": "NEEDS_REAUTH",
                "error_code": "BROWSER_DEPENDENCY_MISSING",
            }

    hard_cap = login_timeout_seconds * (1 + max(0, max_extensions))
    warnings: list[str] = []
    completion_reasons: list[str] = []
    final_obs: dict[str, Any] = {}

    try:
        with factory() as pw:
            try:
                browser = pw.chromium.launch(headless=False)
            except Exception as exc:
                return {
                    "session_status": "NEEDS_REAUTH",
                    "error_code": "BROWSER_OPEN_FAILED",
                    "error": str(exc)[:200],
                }

            browser_closed = False
            try:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    try:
                        try:
                            page.goto(_TARGET_URL, wait_until="domcontentloaded", timeout=15000)
                        except Exception as exc:
                            warnings.append(f"goto_warn:{str(exc)[:100]}")

                        # bring_to_front best-effort
                        try:
                            page.bring_to_front()
                        except Exception:
                            pass

                        initial = _observe(page, max_html_chars=500_000)
                        deadline = time_mod.monotonic() + login_timeout_seconds
                        hard_deadline = time_mod.monotonic() + hard_cap
                        last_obs = initial
                        sixty_warned = False
                        extensions_used = 0
                        last_url = initial.get("current_url", "")
                        last_login_hint = initial.get("login_required_hint", False)

                        # ── 대기 루프 (browser.close 호출 전) ────────────────
                        while True:
                            now = time_mod.monotonic()

                            if now >= hard_deadline:
                                break

                            if now >= deadline:
                                if extend_on_activity and extensions_used < max_extensions:
                                    cur_url = last_obs.get("current_url", "")
                                    cur_hint = last_obs.get("login_required_hint", True)
                                    activity = (cur_url != last_url or cur_hint != last_login_hint)
                                    if activity:
                                        extension = poll_interval_seconds * 5
                                        new_dl = min(deadline + extension, hard_deadline)
                                        if new_dl > deadline:
                                            deadline = new_dl
                                            extensions_used += 1
                                            last_url = cur_url
                                            last_login_hint = cur_hint
                                            continue
                                break

                            remaining = deadline - now
                            if remaining <= 60 and not sixty_warned:
                                sixty_warned = True
                                print(
                                    "[observe_kakao_apps] 로그인 대기 시간이 60초 남았습니다",
                                    file=sys.stderr,
                                )

                            sleep_for = min(poll_interval_seconds, deadline - now)
                            if sleep_for > 0:
                                time_mod.sleep(sleep_for)

                            last_obs = _observe(page, max_html_chars=500_000)
                            completion_reasons = _detect_completion(
                                initial=initial, current=last_obs,
                                success_urls=_SUCCESS_URL_TOKENS,
                                success_texts=_SUCCESS_TEXT_TOKENS,
                            )
                            last_url = last_obs.get("current_url", last_url)
                            last_login_hint = last_obs.get("login_required_hint", last_login_hint)

                            if _is_strong_login_signal(completion_reasons):
                                break

                        # ── 로그인 완료 판정 ──────────────────────────────────
                        has_signal = _has_post_login_signal(last_obs, initial)
                        login_confirmed = False

                        if interactive_mode:
                            # 대화형: 사용자 Enter 확인 (브라우저는 유지)
                            try:
                                ans = input_fn(_LOGIN_COMPLETE_PROMPT)
                                if (ans or "").strip().lower() not in {"n", "no", "아니오"}:
                                    login_confirmed = True
                                    if "user_confirmed_login" not in completion_reasons:
                                        completion_reasons.append("user_confirmed_login")
                            except (EOFError, KeyboardInterrupt):
                                pass
                        else:
                            # 비대화형(Claude Code): signal 기반으로만 판정
                            # input() 호출하지 않음 — 브라우저를 즉시 닫지 않는다
                            login_confirmed = has_signal

                        success = login_confirmed or has_signal

                        if success:
                            # 로그인 성공: 현재 페이지에서 앱 목록 관찰
                            final_obs = _observe(page, max_html_chars=500_000)

                        # 대화형 모드에서만 닫기 전 확인 프롬프트
                        if interactive_mode:
                            try:
                                input_fn(_BROWSER_CLOSE_PROMPT)
                            except (EOFError, KeyboardInterrupt):
                                pass
                        # 비대화형: finally에서 자동으로 _safe_close 호출됨

                    finally:
                        _safe_close(page)
                finally:
                    _safe_close(context)
            finally:
                _safe_close(browser)
                browser_closed = True

    except Exception as exc:
        return {
            "session_status": "NEEDS_REAUTH",
            "error_code": "INTERACTIVE_WAIT_FAILED",
            "error": str(exc)[:200],
        }

    if not success:  # type: ignore[possibly-undefined]
        return {
            "session_status": "NEEDS_REAUTH_TIMEOUT",
            "completion_reasons": completion_reasons,
            "warnings": warnings,
        }

    return {
        "session_status": "READY_LOGGED_IN",
        "final_obs": final_obs,
        "completion_reasons": completion_reasons,
        "warnings": warnings,
    }


# ── main observe ───────────────────────────────────────────────────────────

def observe(
    out_dir: str = "runs/developer_console",
    profile_name: str = _PROFILE_NAME,
    timeout_ms: int = 20_000,
    capture_screenshot: bool = True,
    interactive_login: bool = False,
    login_timeout_seconds: int = 300,
    extend_on_activity: bool = True,
    *,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _clock: Any = None,
    _input_reader: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(out_dir) / f"kakao_apps_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "screenshots").mkdir(exist_ok=True)

    session_status = _check_session_health()
    pending_task_path: str | None = None

    raw: dict[str, Any] = {}
    signals: dict[str, bool] = {
        "apps_visible": False,
        "kakao_login_menu_found": False,
        "consent_items_menu_found": False,
        "business_app_menu_found": False,
        "kakao_sync_menu_found": False,
        "redirect_uri_menu_found": False,
        "platform_menu_found": False,
        "permission_request_menu_found": False,
    }
    app_count_observed = 0
    first_app_observed: str | None = None
    safe_raw: dict[str, Any] = {}

    if session_status in ("NEEDS_REAUTH", "UNKNOWN") and interactive_login:
        wait_result = _interactive_wait(
            login_timeout_seconds=login_timeout_seconds,
            extend_on_activity=extend_on_activity,
            _browser_factory=_browser_factory,
            _clock=_clock,
            _input_reader=_input_reader,
        )
        session_status = wait_result.get("session_status", "NEEDS_REAUTH")
        if session_status == "READY_LOGGED_IN":
            final_obs = wait_result.get("final_obs") or {}
            raw = {
                "success": True,
                "text_excerpt": (final_obs.get("page_structure") or {}).get("visible_text", "")[:8000],
                "title": final_obs.get("title", ""),
                "links": [],
                "buttons": [],
                "warnings": wait_result.get("warnings") or [],
            }
            # Extract text from page structure for signal detection
            struct = final_obs.get("page_structure") or {}
            links_raw = struct.get("links") or []
            buttons_raw = struct.get("buttons") or []
            raw["links"] = [{"text": lnk.get("text", "")[:80], "href": lnk.get("href", "")}
                            for lnk in links_raw[:20]]
            raw["buttons"] = [{"text": btn.get("text", "")[:80]} for btn in buttons_raw[:20]]
            # Title as text_excerpt if empty
            if not raw["text_excerpt"]:
                raw["text_excerpt"] = final_obs.get("title", "")
            # Add login_hint info to signals
            login_text = raw["title"] + " " + raw["text_excerpt"]
            if _contains_any(login_text, _AUTH_TOKENS):
                pass  # already READY_LOGGED_IN
            elif _contains_any(login_text, _LOGIN_TOKENS):
                session_status = "NEEDS_REAUTH"

    elif session_status == "READY_LOGGED_IN":
        try:
            from local_agent.browser_observer import observe_public_browser_page
            raw = observe_public_browser_page(
                _TARGET_URL,
                timeout_ms=timeout_ms,
                max_text_chars=8_000,
                capture_screenshot=capture_screenshot,
                wait_until="networkidle",
            )
        except Exception as exc:
            raw = {"success": False, "error_code": str(exc), "warnings": [str(exc)]}

        safe_raw_inner = _sanitize(raw)
        login_state = _classify_login_state(raw)
        if login_state == "NEEDS_REAUTH":
            session_status = "NEEDS_REAUTH"

    if raw:
        safe_raw = _sanitize(raw)
        signals = _extract_signals(raw)
        links = raw.get("links") or []
        app_names = [
            lnk.get("text", "") for lnk in links
            if "/console/app/" in lnk.get("href", "")
        ]
        app_count_observed = len(app_names)
        if app_names:
            first_app_observed = app_names[0][:80]

    if session_status in ("NEEDS_REAUTH", "NEEDS_REAUTH_TIMEOUT", "UNKNOWN"):
        pt = _create_pending_task(run_dir, session_status)
        pending_task_path = str(pt)

    next_actions = _build_next_actions(session_status, signals)

    output: dict[str, Any] = {
        "console_name": _CONSOLE_NAME,
        "profile_name": profile_name,
        "target_url": _TARGET_URL,
        "observed_at": ts,
        "session_status": session_status,
        "interactive_login_used": interactive_login and session_status in (
            "READY_LOGGED_IN", "NEEDS_REAUTH_TIMEOUT"
        ),
        "pending_task_created": pending_task_path is not None,
        "pending_task_path": pending_task_path,
        "app_count_observed": app_count_observed,
        "first_app_observed": first_app_observed,
        "secret_like_values_captured": safe_raw.get("secret_like_detected", False),
        "next_actions": next_actions,
        "warnings": list(raw.get("warnings") or []),
        **signals,
    }
    output["screenshots"] = (
        [raw["screenshot_path"]] if raw.get("screenshot_path") else []
    )

    _write_results(output, run_dir)
    return output


def _write_results(output: dict, run_dir: Path) -> None:
    (run_dir / "apps.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "apps.md").write_text(_build_md(output), encoding="utf-8")
    (run_dir / "next_actions.md").write_text(
        _build_next_actions_md(output["next_actions"]), encoding="utf-8"
    )


def _build_md(o: dict) -> str:
    lines = [
        "# Kakao 앱 목록 관찰 결과 (KAKAO-DEV-3R)",
        "",
        f"- observed_at: {o['observed_at']}",
        f"- session_status: {o['session_status']}",
        f"- interactive_login_used: {o.get('interactive_login_used')}",
        f"- pending_task_created: {o['pending_task_created']}",
        f"- pending_task_path: {o['pending_task_path']}",
        f"- app_count_observed: {o['app_count_observed']}",
        f"- first_app_observed: {o['first_app_observed']}",
        f"- apps_visible: {o.get('apps_visible')}",
        f"- kakao_login_menu_found: {o.get('kakao_login_menu_found')}",
        f"- consent_items_menu_found: {o.get('consent_items_menu_found')}",
        f"- platform_menu_found: {o.get('platform_menu_found')}",
        f"- redirect_uri_menu_found: {o.get('redirect_uri_menu_found')}",
        f"- permission_request_menu_found: {o.get('permission_request_menu_found')}",
        f"- business_app_menu_found: {o.get('business_app_menu_found')}",
        f"- kakao_sync_menu_found: {o.get('kakao_sync_menu_found')}",
        f"- secret_like_values_captured: {o.get('secret_like_values_captured')}",
        "",
        "## 보안 확인",
        "",
        "- 비밀번호/OTP 저장: 없음",
        "- password input value 읽기: 없음",
        "- 쿠키/session/storage 추출: 없음",
        f"- key/secret 원문 감지 및 마스킹: {o.get('secret_like_values_captured')}",
        "- 앱 삭제/secret 재발급: 없음",
        "- 실제 신청 제출: 없음",
    ]
    return "\n".join(lines)


def _build_next_actions_md(actions: list) -> str:
    lines = ["# Kakao 다음 자동화 후보 (KAKAO-DEV-3R)", ""]
    for act in actions:
        lines += [
            f"## {act['task_key']} — {act['title']}",
            f"- auto_executable: {act['auto_executable']}",
            f"- auth_principal_required: {act.get('auth_principal_required') or '없음'}",
            f"- risk_level: {act.get('risk_level', 'LOW')}",
            f"- approval_required: {act.get('approval_required', False)}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="KAKAO-DEV-3R observer")
    parser.add_argument("--out-dir", default="runs/developer_console")
    parser.add_argument("--profile-name", default=_PROFILE_NAME)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--no-screenshot", action="store_true")
    parser.add_argument("--interactive-login", action="store_true", dest="interactive_login",
                        help="NEEDS_REAUTH 시 브라우저를 유지하고 로그인 완료를 감지한다")
    parser.add_argument("--login-timeout-seconds", type=int, default=300,
                        dest="login_timeout_seconds",
                        help="interactive login 대기 최대 시간 (초), 기본 300")
    parser.add_argument("--extend-on-activity", action="store_true", default=True,
                        dest="extend_on_activity")
    parser.add_argument("--keep-open-on-auth-required", action="store_true",
                        dest="keep_open_on_auth_required",
                        help="--interactive-login의 별칭")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    interactive = args.interactive_login or args.keep_open_on_auth_required

    output = observe(
        out_dir=args.out_dir,
        profile_name=args.profile_name,
        timeout_ms=args.timeout_ms,
        capture_screenshot=not args.no_screenshot,
        interactive_login=interactive,
        login_timeout_seconds=args.login_timeout_seconds,
        extend_on_activity=args.extend_on_activity,
    )

    run_dirs = sorted(Path(args.out_dir).glob("kakao_apps_*"), reverse=True)
    if run_dirs:
        rd = run_dirs[0]
        print(f"[결과 디렉터리] {rd}", file=sys.stderr)
        print(f"  apps.json      : {rd / 'apps.json'}", file=sys.stderr)
        print(f"  apps.md        : {rd / 'apps.md'}", file=sys.stderr)
        print(f"  next_actions.md: {rd / 'next_actions.md'}", file=sys.stderr)
        if output.get("pending_task_path"):
            print(f"  pending_task   : {output['pending_task_path']}", file=sys.stderr)

    if args.json_output:
        summary = {k: output[k] for k in (
            "console_name", "profile_name", "target_url", "observed_at",
            "session_status", "interactive_login_used",
            "pending_task_created", "pending_task_path",
            "app_count_observed", "first_app_observed", "apps_visible",
            "kakao_login_menu_found", "consent_items_menu_found",
            "platform_menu_found", "redirect_uri_menu_found",
            "permission_request_menu_found", "business_app_menu_found",
            "kakao_sync_menu_found", "secret_like_values_captured",
        ) if k in output}
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
