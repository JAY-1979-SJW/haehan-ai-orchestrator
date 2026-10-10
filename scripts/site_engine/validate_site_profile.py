"""
사이트 profile 유효성 검사 도구

등록된 site profile이 보안 정책을 준수하는지 검사한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.agent_runtime.runtime.site_profile.site_profile_registry import (  # noqa: E402
    _COMMON_BLOCKED,
    _REGISTRY,
)

_FORBIDDEN_NOTES_KEYWORDS = [
    "password",
    "otp",
    "cookie",
    "session",
    "token",
    "cert_password",
    "npki",
    "captcha",
    "storage_state",
    "auto_sign",
    "auto_bid",
    "auto_payment",
]

_FORBIDDEN_DELEGATED_ACTIONS = frozenset(
    [
        "password_save",
        "otp_save",
        "cert_password_save",
        "cookie_export",
        "session_export",
        "token_export",
        "storage_state_export",
        "cert_file_access",
        "npki_access",
        "captcha_bypass",
        "account_bypass",
        "stealth_evasion",
        "auto_payment",
        "auto_transfer",
        "auto_bid_submit",
        "auto_esign",
    ]
)

_REQUIRED_SAFE_CAPABILITY = frozenset(
    [
        "READONLY_EXPLORE",
        "SEARCH",
        "EXTRACT_TEXT",
    ]
)


def validate_profile(profile: dict) -> dict:
    errors = []
    warnings = []

    # 필수 필드
    for field in (
        "site_id",
        "display_name",
        "domains",
        "category",
        "login_policy",
        "supported_capabilities",
        "delegated_actions",
        "blocked_actions",
        "direct_required_actions",
        "requires_audit_log",
    ):
        if field not in profile:
            errors.append(f"필수 필드 누락: {field}")

    # blocked_actions에 _COMMON_BLOCKED 포함 여부
    blocked = set(profile.get("blocked_actions", []))
    missing_blocked = set(_COMMON_BLOCKED) - blocked
    if missing_blocked:
        errors.append(f"blocked_actions에서 공통 금지 action 누락: {missing_blocked}")

    # delegated_actions에 금지 action 포함 여부
    delegated = set(profile.get("delegated_actions", []))
    forbidden_delegated = delegated & _FORBIDDEN_DELEGATED_ACTIONS
    if forbidden_delegated:
        errors.append(f"delegated_actions에 금지 action 포함: {forbidden_delegated}")

    # max_executions 한도
    max_exec = profile.get("max_default_executions", 1)
    if max_exec > 50:
        errors.append(f"max_default_executions 초과 (최대 50): {max_exec}")

    # notes에 민감 키워드
    notes = profile.get("notes", "").lower()
    for kw in _FORBIDDEN_NOTES_KEYWORDS:
        if kw in notes:
            warnings.append(f"notes에 민감 키워드 포함 (검토 필요): '{kw}'")

    # requires_audit_log = True 강제
    if not profile.get("requires_audit_log", False):
        errors.append("requires_audit_log가 False — 감사 로그는 필수")

    # server_browser_used 필드가 있으면 False여야 함
    if profile.get("server_browser_used") is True:
        errors.append("server_browser_used=True 금지 (로컬 브라우저만 허용)")

    ok = len(errors) == 0
    return {
        "site_id": profile.get("site_id", "UNKNOWN"),
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
    }


def validate_all_registered() -> list[dict]:
    results = []
    for site_id, profile in _REGISTRY.items():
        result = validate_profile(profile)
        results.append(result)
    return results


def print_validation_report(results: list[dict]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed

    print("\n=== Site Profile 유효성 검사 ===")
    print(f"총 {total}개 | 통과 {passed}개 | 실패 {failed}개\n")

    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        print(f"[{status}] {r['site_id']}")
        for e in r["errors"]:
            print(f"  ERROR: {e}")
        for w in r["warnings"]:
            print(f"  WARN:  {w}")

    if failed > 0:
        print(f"\n검사 실패: {failed}개 profile 수정 필요")
    else:
        print("\n모든 profile 정책 준수 확인 완료.")


if __name__ == "__main__":
    results = validate_all_registered()
    print_validation_report(results)
    any_fail = any(not r["ok"] for r in results)
    sys.exit(1 if any_fail else 0)
