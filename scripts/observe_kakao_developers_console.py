"""KAKAO-DEV-2 — Kakao Developers 콘솔 read-only observer.

Claude Code가 직접 실행한다. 대표님에게 터미널 명령/파일 확인을 요구하지 않는다.

허용:
  - 브라우저 열기 / URL 접속 / 스크린샷 저장
  - 텍스트/링크/버튼 요약 / 로그인 상태 관찰
  - 앱 목록·메뉴 관찰 / 다음 자동화 후보 산출

절대 금지:
  - 비밀번호/OTP 자동 입력
  - 쿠키/session/storage_state 추출
  - API key / Client Secret 원문 저장
  - 앱 삭제 / Secret 재발급·폐기
  - 실제 권한 신청 제출
  - 결제/광고/메시지 발송
  - 외부 사용자 대상 write action

인증 화면이 나오면:
  - NEEDS_AUTH_PRINCIPAL (developer_console_operator) 로 분류
  - 대표님에게 로그인 요구하지 않음
  - 우회 시도하지 않음
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_agent.browser_observer import observe_public_browser_page

_CONSOLE_NAME = "kakao_developers"
_TARGET_URL = "https://developers.kakao.com/"
_APP_LIST_URL = "https://developers.kakao.com/console/app"

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
_KAKAO_LOGIN_MENU_TOKENS = (
    "카카오 로그인", "kakao login",
)
_CONSENT_MENU_TOKENS = (
    "동의항목", "consent", "개인정보 동의",
)
_BIZ_APP_TOKENS = (
    "비즈앱", "비즈니스 앱", "biz app",
)
_KAKAO_SYNC_TOKENS = (
    "카카오싱크", "kakao sync",
)
_REDIRECT_URI_TOKENS = (
    "redirect uri", "redirect_uri", "리다이렉트",
)
_PLATFORM_DOMAIN_TOKENS = (
    "플랫폼", "platform", "도메인 등록", "web platform",
)
_PERMISSION_MENU_TOKENS = (
    "권한 신청", "추가 기능", "비즈니스 권한", "business", "permission request",
)


def _has_secret_like(text: str) -> bool:
    return bool(_SECRET_PATTERN.search(text))


def _mask_secrets(text: str) -> str:
    return _SECRET_PATTERN.sub("[MASKED]", text)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(t.lower() in lower for t in tokens)


def _classify_login_state(result: dict) -> str:
    text = (result.get("text_excerpt") or "").lower()
    title = (result.get("title") or "").lower()
    page_state = result.get("page_state", "")
    combined = text + " " + title

    if page_state in ("login_required",):
        return "login_required"
    if _contains_any(combined, _AUTH_TOKENS):
        return "logged_in"
    if _contains_any(combined, _LOGIN_TOKENS):
        return "login_required"
    return "unknown"


def _extract_menu_signals(result: dict) -> dict[str, bool]:
    text = (result.get("text_excerpt") or "").lower()
    title = (result.get("title") or "").lower()
    links = [lnk.get("text", "") for lnk in (result.get("links") or [])]
    buttons = [btn.get("text", "") for btn in (result.get("buttons") or [])]
    combined = text + " " + title + " " + " ".join(links + buttons)

    return {
        "apps_visible": _contains_any(combined, _APP_LIST_TOKENS),
        "kakao_login_menu_found": _contains_any(combined, _KAKAO_LOGIN_MENU_TOKENS),
        "consent_items_menu_found": _contains_any(combined, _CONSENT_MENU_TOKENS),
        "business_app_menu_found": _contains_any(combined, _BIZ_APP_TOKENS),
        "kakao_sync_menu_found": _contains_any(combined, _KAKAO_SYNC_TOKENS),
        "redirect_uri_menu_found": _contains_any(combined, _REDIRECT_URI_TOKENS),
        "platform_domain_menu_found": _contains_any(combined, _PLATFORM_DOMAIN_TOKENS),
        "permission_request_menu_found": _contains_any(combined, _PERMISSION_MENU_TOKENS),
    }


def _build_next_actions(login_state: str, signals: dict) -> list[dict]:
    actions = []
    if login_state == "login_required":
        actions.append({
            "task_key": "KAKAO-DEV-2-AUTH",
            "title": "developer_console_operator 인증 후 재관찰",
            "auto_executable": False,
            "auth_principal_required": "developer_console_operator",
            "risk_level": "LOW",
            "approval_required": False,
            "notes": "인증 주체 준비 후 Claude Code가 자율 진행",
        })
    if login_state == "logged_in" or signals.get("apps_visible"):
        actions.append({
            "task_key": "KAKAO-DEV-3",
            "title": "앱 설정 상태 관찰 (platform, redirect URI, login 활성화)",
            "auto_executable": True,
            "auth_principal_required": None,
            "risk_level": "LOW",
            "approval_required": False,
            "notes": "Claude Code 자율 실행 — read-only 관찰",
        })
    actions.append({
        "task_key": "KAKAO-DEV-4",
        "title": "권한 신청서 draft builder",
        "auto_executable": True,
        "auth_principal_required": None,
        "risk_level": "LOW",
        "approval_required": False,
        "notes": "신청서 작성만, 제출은 KAKAO-DEV-5",
    })
    actions.append({
        "task_key": "KAKAO-DEV-5",
        "title": "권한 신청서 제출 자동화",
        "auto_executable": False,
        "auth_principal_required": "developer_console_operator",
        "risk_level": "MEDIUM",
        "approval_required": True,
        "notes": "인증 주체 준비 후 자율 진행. 제출 전 승인 확인.",
    })
    actions.append({
        "task_key": "KAKAO-DEV-6",
        "title": "심사 상태 모니터링",
        "auto_executable": False,
        "auth_principal_required": "developer_console_operator",
        "risk_level": "LOW",
        "approval_required": False,
        "notes": "인증 주체 준비 후 Claude Code가 자율 진행",
    })
    actions.append({
        "task_key": "KAKAO-OAUTH-1",
        "title": "Kakao OAuth local callback/token flow 설계",
        "auto_executable": True,
        "auth_principal_required": None,
        "risk_level": "LOW",
        "approval_required": False,
        "notes": "설계 문서 + 코드 초안 생성. 실제 token 발급은 별도 단계.",
    })
    actions.append({
        "task_key": "SECRET-OPS-1",
        "title": "Kakao REST API key / Client Secret safe env 등록",
        "auto_executable": True,
        "auth_principal_required": None,
        "risk_level": "MEDIUM",
        "approval_required": False,
        "notes": "safe env setter 경유. 원문 출력 절대 금지.",
    })
    return actions


def _sanitize_result_for_output(result: dict) -> dict:
    """secret-like 값을 마스킹하고 안전한 필드만 남긴다."""
    safe = {}
    for k in (
        "success", "error_code", "warnings", "page_state",
        "title", "status_code", "text_length",
        "links_count", "buttons_count", "forms_count", "inputs_count",
        "screenshot_path",
    ):
        if k in result:
            safe[k] = result[k]

    text = result.get("text_excerpt", "") or ""
    if _has_secret_like(text):
        safe["text_excerpt"] = _mask_secrets(text[:500])
        safe["secret_like_detected_in_text"] = True
    else:
        safe["text_excerpt"] = text[:500]
        safe["secret_like_detected_in_text"] = False

    safe["links"] = [
        {"text": lnk.get("text", "")[:80]}
        for lnk in (result.get("links") or [])[:20]
    ]
    safe["buttons"] = [
        {"text": btn.get("text", "")[:80]}
        for btn in (result.get("buttons") or [])[:20]
    ]
    return safe


def observe(
    url: str = _TARGET_URL,
    out_dir: str = "runs/developer_console",
    profile_name: str = "kakao_developer_console",
    timeout_ms: int = 20_000,
    capture_screenshot: bool = True,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(out_dir) / f"kakao_observe_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    screenshot_path = str(screenshots_dir / "main.png") if capture_screenshot else None

    raw = observe_public_browser_page(
        url,
        timeout_ms=timeout_ms,
        max_text_chars=8_000,
        capture_screenshot=capture_screenshot,
        wait_until="networkidle",
    )

    safe_raw = _sanitize_result_for_output(raw)
    login_state = _classify_login_state(raw)
    signals = _extract_menu_signals(raw)
    reachable = bool(raw.get("success") or raw.get("status_code") in (200, 301, 302))
    next_actions = _build_next_actions(login_state, signals)

    output: dict[str, Any] = {
        "console_name": _CONSOLE_NAME,
        "target_url": url,
        "observed_at": ts,
        "login_state": login_state,
        "auth_principal_required": login_state != "logged_in",
        "auth_principal_type": "developer_console_operator" if login_state != "logged_in" else None,
        "reachable": reachable,
        "app_count_observed": 0,
        "secret_like_values_captured": safe_raw.get("secret_like_detected_in_text", False),
        "menus": safe_raw.get("links", []) + safe_raw.get("buttons", []),
        "recommended_next_actions": next_actions,
        "warnings": list(raw.get("warnings") or []),
        "page_observation": safe_raw,
        **signals,
    }

    if raw.get("screenshot_path"):
        output["screenshots"] = [raw["screenshot_path"]]
    else:
        output["screenshots"] = []

    _write_results(output, next_actions, run_dir)
    return output


def _write_results(output: dict, next_actions: list, run_dir: Path) -> None:
    observe_json = run_dir / "observe.json"
    observe_json.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    menu_map_json = run_dir / "menu_map.json"
    menu_map_json.write_text(
        json.dumps(output.get("menus", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    next_actions_md = run_dir / "next_actions.md"
    next_actions_md.write_text(_build_next_actions_md(next_actions), encoding="utf-8")

    observe_md = run_dir / "observe.md"
    observe_md.write_text(_build_observe_md(output), encoding="utf-8")


def _build_observe_md(output: dict) -> str:
    lines = [
        "# Kakao Developers 콘솔 관찰 결과 (KAKAO-DEV-2)",
        "",
        f"- observed_at: {output.get('observed_at')}",
        f"- target_url: {output.get('target_url')}",
        f"- login_state: {output.get('login_state')}",
        f"- auth_principal_required: {output.get('auth_principal_required')}",
        f"- auth_principal_type: {output.get('auth_principal_type')}",
        f"- reachable: {output.get('reachable')}",
        f"- apps_visible: {output.get('apps_visible')}",
        f"- kakao_login_menu_found: {output.get('kakao_login_menu_found')}",
        f"- consent_items_menu_found: {output.get('consent_items_menu_found')}",
        f"- business_app_menu_found: {output.get('business_app_menu_found')}",
        f"- kakao_sync_menu_found: {output.get('kakao_sync_menu_found')}",
        f"- redirect_uri_menu_found: {output.get('redirect_uri_menu_found')}",
        f"- platform_domain_menu_found: {output.get('platform_domain_menu_found')}",
        f"- permission_request_menu_found: {output.get('permission_request_menu_found')}",
        f"- secret_like_values_captured: {output.get('secret_like_values_captured')}",
        "",
        "## 상태 분류",
        "",
    ]
    login_state = output.get("login_state", "unknown")
    if login_state == "logged_in":
        lines += ["- **READY_AUTOMATED**: 로그인됨, 앱/권한 메뉴 접근 가능"]
    elif login_state == "login_required":
        lines += [
            "- **NEEDS_AUTH_PRINCIPAL**: developer_console_operator 인증 필요",
            "- 대표님에게 로그인 요구하지 않음. 인증 주체 준비 후 Claude Code 자율 진행.",
        ]
    else:
        lines += ["- **NEEDS_AUTH_PRINCIPAL**: 로그인 상태 불명확. 인증 주체 준비 후 재관찰 필요."]

    lines += [
        "",
        "## 보안 확인",
        "",
        "- 비밀번호/OTP 저장: 없음",
        "- 쿠키/session/storage 추출: 없음",
        f"- key/secret 원문 감지 및 마스킹: {output.get('secret_like_values_captured')}",
        "- 앱 삭제/secret 재발급: 없음",
        "- 실제 신청 제출: 없음",
        "- 외부 write action: 없음",
        "",
    ]

    warnings = output.get("warnings") or []
    if warnings:
        lines.append("## 경고")
        lines += [f"- {w}" for w in warnings]
        lines.append("")

    return "\n".join(lines)


def _build_next_actions_md(next_actions: list) -> str:
    lines = [
        "# Kakao Developers 다음 자동화 후보 (KAKAO-DEV-2 산출)",
        "",
        "Claude Code 자율 실행 기준: READY 항목은 Claude Code가 직접 실행. "
        "NEEDS_AUTH_PRINCIPAL 항목은 인증 주체 준비 후 Claude Code가 자율 진행.",
        "",
    ]
    for act in next_actions:
        lines += [
            f"## {act['task_key']} — {act['title']}",
            f"- auto_executable: {act['auto_executable']}",
            f"- auth_principal_required: {act.get('auth_principal_required') or '없음'}",
            f"- risk_level: {act['risk_level']}",
            f"- approval_required: {act['approval_required']}",
            f"- notes: {act['notes']}",
            "",
        ]
    return "\n".join(lines)


def _print_summary(output: dict) -> None:
    summary = {
        "console_name": output["console_name"],
        "target_url": output["target_url"],
        "login_state": output["login_state"],
        "auth_principal_required": output["auth_principal_required"],
        "reachable": output["reachable"],
        "apps_visible": output.get("apps_visible"),
        "kakao_login_menu_found": output.get("kakao_login_menu_found"),
        "consent_items_menu_found": output.get("consent_items_menu_found"),
        "business_app_menu_found": output.get("business_app_menu_found"),
        "secret_like_values_captured": output.get("secret_like_values_captured"),
        "warnings": output.get("warnings"),
        "next_action_count": len(output.get("recommended_next_actions", [])),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="KAKAO-DEV-2 observer")
    parser.add_argument("--url", default=_TARGET_URL)
    parser.add_argument("--out-dir", default="runs/developer_console")
    parser.add_argument("--profile-name", default="kakao_developer_console")
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--no-screenshot", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    output = observe(
        url=args.url,
        out_dir=args.out_dir,
        profile_name=args.profile_name,
        timeout_ms=args.timeout_ms,
        capture_screenshot=not args.no_screenshot,
    )

    run_dir_path = next(
        (Path(args.out_dir) / d for d in sorted(
            (Path(args.out_dir)).iterdir(),
            reverse=True,
        ) if "kakao_observe_" in d.name),
        None,
    )

    if run_dir_path:
        print(f"[결과 디렉터리] {run_dir_path}", file=sys.stderr)
        print(f"  observe.json : {run_dir_path / 'observe.json'}", file=sys.stderr)
        print(f"  observe.md   : {run_dir_path / 'observe.md'}", file=sys.stderr)
        print(f"  next_actions : {run_dir_path / 'next_actions.md'}", file=sys.stderr)

    if args.json_output:
        _print_summary(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
