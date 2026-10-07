"""Common login/session integrity guard for site automation.

This module is site-neutral.  Site-specific auth helpers can return their normal
result dicts, and live workflows should pass those dicts through this guard
before any browser navigation, scan, prepare, or submit work continues.
"""

from __future__ import annotations

from typing import Any

SESSION_INTEGRITY_FAILURE_REASONS = {
    "different_user_logged_in",
    "session_user_mismatch",
    "account_mismatch",
    "unexpected_account",
    "wrong_user",
    "stale_session",
    "expired_session",
    "invalid_session",
    "login_required_after_restore",
}

SESSION_INTEGRITY_FAILURE_TOKENS = {
    "different_user",
    "user_mismatch",
    "account_mismatch",
    "wrong_user",
    "stale_session",
    "expired_session",
    "invalid_session",
}


class SessionIntegrityBlocked(RuntimeError):
    """Raised when a site workflow must stop because login/session state is unsafe."""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        site = result.get("site") or "site"
        reason = result.get("reason") or "session_integrity_failed"
        super().__init__(f"{site} session integrity blocked: {reason}")


def _stringify(value: Any) -> str:
    return str(value or "").strip().lower()


def is_session_integrity_failure(auth_result: dict[str, Any] | None) -> bool:
    if not auth_result:
        return False
    reason = _stringify(auth_result.get("reason") or auth_result.get("error"))
    if reason in SESSION_INTEGRITY_FAILURE_REASONS:
        return True
    return any(token in reason for token in SESSION_INTEGRITY_FAILURE_TOKENS)


def build_session_integrity_result(
    auth_result: dict[str, Any] | None,
    *,
    site: str,
    workflow: str = "",
    expected_user: str = "",
) -> dict[str, Any]:
    auth_result = dict(auth_result or {})
    failure = is_session_integrity_failure(auth_result)
    actual_user = str(auth_result.get("user") or auth_result.get("actual_user") or "")
    expected = expected_user or str(auth_result.get("expected_user") or "")
    if expected and actual_user and expected != actual_user:
        failure = True
        auth_result.setdefault("reason", "session_user_mismatch")
    return {
        "ok": not failure,
        "blocked": failure,
        "site": site,
        "workflow": workflow,
        "reason": auth_result.get("reason") or auth_result.get("error") or "",
        "expected_user": expected,
        "actual_user": actual_user,
        "auth_ok": bool(auth_result.get("ok")),
    }


def emit_session_integrity_event(result: dict[str, Any]) -> None:
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            "SITE_SESSION_INTEGRITY_BLOCKED",
            site=result.get("site") or "",
            workflow=result.get("workflow") or "",
            status="blocked",
            risk="auth_session",
            message="Login/session integrity failed; live workflow stopped",
            metadata={
                "reason": result.get("reason"),
                "expected_user": result.get("expected_user"),
                "actual_user": result.get("actual_user"),
                "auth_ok": result.get("auth_ok"),
            },
        )
    except Exception:  # noqa: BLE001 - 세션 무결성 위반 텔레메트리 전송(emit_session_integrity_event) 실패를 흡수하는 except — 실제 차단(raise SessionIntegrityBlocked)은 이 except 밖의 assert_session_integrity에서 무조건 수행되므로 이 except가 차단 여부에 영향을 주지 않음.
        pass


def assert_session_integrity(
    auth_result: dict[str, Any] | None,
    *,
    site: str,
    workflow: str = "",
    expected_user: str = "",
) -> dict[str, Any]:
    result = build_session_integrity_result(
        auth_result,
        site=site,
        workflow=workflow,
        expected_user=expected_user,
    )
    if result["blocked"]:
        emit_session_integrity_event(result)
        raise SessionIntegrityBlocked(result)
    return result
