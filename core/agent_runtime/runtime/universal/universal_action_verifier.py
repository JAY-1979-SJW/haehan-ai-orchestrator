"""Universal Action Verifier — 실행 후 결과를 검증한다."""
from __future__ import annotations

from typing import Any

from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_WARN,
)

_SAFE_FIELDS = [
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
]

_BLOCKED_ACTIONS = frozenset([
    "password_save", "otp_save", "cert_password_save",
    "cookie_export", "session_export", "token_export", "storage_state_export",
    "cert_file_access", "npki_access", "captcha_bypass", "account_bypass",
    "stealth_evasion", "bulk_spam_post", "bulk_spam_comment",
    "auto_payment", "auto_transfer", "auto_bid_submit", "auto_esign",
])


def verify_action_result(
    action: str,
    result: dict[str, Any],
    before_observation: dict[str, Any] | None = None,
    after_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    action 실행 결과를 검증한다.

    반환:
      verified: bool
      status: str
      checks: dict[str, bool]
      violations: list[str]
      safe_fields_ok: bool
    """
    violations = []
    checks: dict[str, bool] = {}

    # 1. safe field 검사
    safe_fields_ok = True
    for field in _SAFE_FIELDS:
        val = result.get(field)
        if val is True:
            violations.append(f"safe field 위반: {field} = True")
            safe_fields_ok = False
        checks[field] = (val is not True)

    # 2. blocked action 실행 여부
    checks["blocked_action_not_executed"] = action not in _BLOCKED_ACTIONS
    if action in _BLOCKED_ACTIONS and result.get("ok") is True:
        violations.append(f"BLOCKED action이 실행됨: {action}")

    # 3. audit log 존재
    has_audit = bool(result.get("audit_log_ids"))
    checks["audit_log_exists"] = has_audit

    # 4. 상태 기반 검사
    status = result.get("status", STATUS_FAILED)
    checks["status_not_failed"] = status not in (STATUS_FAILED, "FAILED")

    # 5. 페이지 변화 검증 (observation이 있는 경우)
    if before_observation and after_observation:
        url_changed = before_observation.get("url") != after_observation.get("url")
        title_changed = before_observation.get("title") != after_observation.get("title")
        checks["page_changed"] = url_changed or title_changed
    else:
        checks["page_changed"] = None  # type: ignore[assignment]

    # 6. 다운로드 검증
    if action == "download_document":
        manifest = result.get("safe_outputs", {}).get("download_manifest", [])
        checks["download_manifest_exists"] = bool(manifest)

    # 7. draft/preview 검증
    if action in ("generate_draft", "save_draft"):
        draft = result.get("safe_outputs", {}).get("draft_content") or result.get("safe_outputs", {})
        checks["draft_created"] = bool(draft)

    verified = len(violations) == 0

    return {
        "verified": verified,
        "status": STATUS_COMPLETED if verified else STATUS_WARN,
        "checks": checks,
        "violations": violations,
        "safe_fields_ok": safe_fields_ok,
    }


def verify_no_sensitive_data(result: dict[str, Any]) -> list[str]:
    """결과에 민감 데이터가 없는지 확인."""
    violations = []
    for field in _SAFE_FIELDS:
        if result.get(field) is True:
            violations.append(f"{field} = True")
    return violations


def verify_plan_execution(
    plan: dict[str, Any],
    executed_actions: list[str],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """계획된 action들이 올바르게 실행되었는지 검증."""
    plan_actions = [s["action"] for s in plan.get("steps", []) if s.get("executable")]
    violations = []

    # blocked action이 실행됐는지
    for action in executed_actions:
        if action in _BLOCKED_ACTIONS:
            violations.append(f"BLOCKED action 실행됨: {action}")

    # safe fields
    all_safe = True
    for r in results:
        r_violations = verify_no_sensitive_data(r)
        violations.extend(r_violations)
        if r_violations:
            all_safe = False

    return {
        "plan_actions": plan_actions,
        "executed_actions": executed_actions,
        "all_safe": all_safe,
        "violations": violations,
        "verified": len(violations) == 0,
    }
