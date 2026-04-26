"""KAKAO-DEV-3R — 전용 프로필 기반 Kakao 앱 목록 관찰.

전용 프로필(kakao_developer_console)을 사용해 Kakao Developers 앱 목록을 관찰한다.
- READY_LOGGED_IN: 앱 목록/앱 설정 메뉴 관찰 진행
- NEEDS_REAUTH: pending task JSON 생성 후 재개 가능 상태로 남긴다

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        "auto_executable": False,
        "auth_principal_required": "developer_console_operator",
        "notes": "세션 갱신(로그인) 후 scripts/observe_kakao_apps.py 재실행",
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
    if session_status in ("NEEDS_REAUTH", "UNKNOWN"):
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


def observe(
    out_dir: str = "runs/developer_console",
    profile_name: str = _PROFILE_NAME,
    timeout_ms: int = 20_000,
    capture_screenshot: bool = True,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(out_dir) / f"kakao_apps_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

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

    if session_status == "READY_LOGGED_IN":
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

        safe_raw = _sanitize(raw)
        login_state = _classify_login_state(raw)
        if login_state == "NEEDS_REAUTH":
            session_status = "NEEDS_REAUTH"
        signals = _extract_signals(raw)

        links = raw.get("links") or []
        app_names = [
            lnk.get("text", "") for lnk in links
            if lnk.get("href", "").startswith("https://developers.kakao.com/console/app/")
        ]
        app_count_observed = len(app_names)
        if app_names:
            first_app_observed = app_names[0][:80]

    if session_status in ("NEEDS_REAUTH", "UNKNOWN"):
        pt = _create_pending_task(run_dir, session_status)
        pending_task_path = str(pt)

    next_actions = _build_next_actions(session_status, signals)

    output: dict[str, Any] = {
        "console_name": _CONSOLE_NAME,
        "profile_name": profile_name,
        "target_url": _TARGET_URL,
        "observed_at": ts,
        "session_status": session_status,
        "pending_task_created": pending_task_path is not None,
        "pending_task_path": pending_task_path,
        "app_count_observed": app_count_observed,
        "first_app_observed": first_app_observed,
        "secret_like_values_captured": safe_raw.get("secret_like_detected", False),
        "next_actions": next_actions,
        "warnings": list(raw.get("warnings") or []),
        **signals,
    }
    if raw.get("screenshot_path"):
        output["screenshots"] = [raw["screenshot_path"]]
    else:
        output["screenshots"] = []

    _write_results(output, run_dir)
    return output


def _write_results(output: dict, run_dir: Path) -> None:
    (run_dir / "apps.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "apps.md").write_text(_build_md(output), encoding="utf-8")
    (run_dir / "next_actions.md").write_text(_build_next_actions_md(output["next_actions"]), encoding="utf-8")


def _build_md(o: dict) -> str:
    lines = [
        "# Kakao 앱 목록 관찰 결과 (KAKAO-DEV-3R)",
        "",
        f"- observed_at: {o['observed_at']}",
        f"- session_status: {o['session_status']}",
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
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    output = observe(
        out_dir=args.out_dir,
        profile_name=args.profile_name,
        timeout_ms=args.timeout_ms,
        capture_screenshot=not args.no_screenshot,
    )

    run_dir = sorted(
        Path(args.out_dir).glob("kakao_apps_*"), reverse=True
    )
    if run_dir:
        print(f"[결과 디렉터리] {run_dir[0]}", file=sys.stderr)
        print(f"  apps.json      : {run_dir[0] / 'apps.json'}", file=sys.stderr)
        print(f"  apps.md        : {run_dir[0] / 'apps.md'}", file=sys.stderr)
        print(f"  next_actions.md: {run_dir[0] / 'next_actions.md'}", file=sys.stderr)
        if output.get("pending_task_path"):
            print(f"  pending_task   : {output['pending_task_path']}", file=sys.stderr)

    if args.json_output:
        summary = {k: output[k] for k in (
            "console_name", "profile_name", "target_url", "observed_at",
            "session_status", "pending_task_created", "pending_task_path",
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
