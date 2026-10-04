"""
공통 로컬 에이전트 task protocol

서버는 이 스키마로 task를 생성한다.
로컬 에이전트는 이 스키마로 task를 수신하고 Playwright로 실행한다.
사이트별 전용 필드 없음. 모든 사이트는 공통 protocol로 처리한다.

금지 필드 (task에 절대 포함하지 않음):
- cookie, session, Authorization, password, otp
- certificate_password, certificate_file_path
- localStorage, sessionStorage, token, npki
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# ── task_type 상수 ─────────────────────────────────────────────────────────────

TASK_TYPE_BROWSER = "browser_task"

# ── execution_mode 상수 ────────────────────────────────────────────────────────

EXEC_MODE_LOCAL_PLAYWRIGHT = "LOCAL_PLAYWRIGHT"

# ── 허용 action ────────────────────────────────────────────────────────────────

ALLOWED_TASK_ACTIONS: frozenset[str] = frozenset({
    "open_url",
    "read_page",
    "search",
    "download_file",
    "capture_screenshot",
    "extract_text",
    "extract_table",
    "wait_for_user_auth",
    "detect_login_status",
})

# ── result status 상수 ─────────────────────────────────────────────────────────

STATUS_COMPLETED = "COMPLETED"
STATUS_WAITING_USER_AUTH = "WAITING_USER_AUTH"
STATUS_USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
STATUS_FAILED = "FAILED"
STATUS_BLOCKED = "BLOCKED"
STATUS_CANCELLED = "CANCELLED"
STATUS_AUTH_COMPLETED = "AUTH_COMPLETED"
STATUS_AUTH_TIMEOUT = "AUTH_TIMEOUT"
STATUS_AUTH_CANCELLED = "AUTH_CANCELLED"
STATUS_AUTH_FAILED = "AUTH_FAILED"
STATUS_AUTO_RESUME_READY = "AUTO_RESUME_READY"

_ALL_STATUSES: frozenset[str] = frozenset({
    STATUS_COMPLETED, STATUS_WAITING_USER_AUTH, STATUS_USER_ACTION_REQUIRED,
    STATUS_FAILED, STATUS_BLOCKED, STATUS_CANCELLED,
    STATUS_AUTH_COMPLETED, STATUS_AUTH_TIMEOUT, STATUS_AUTH_CANCELLED,
    STATUS_AUTH_FAILED, STATUS_AUTO_RESUME_READY,
})

# ── 금지 필드 ──────────────────────────────────────────────────────────────────

_FORBIDDEN_TASK_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "Authorization", "password", "otp",
    "certificate_password", "certificate_file_path", "localStorage",
    "sessionStorage", "token", "access_token", "refresh_token",
    "npki", "private_key", "auth_header",
})

_FORBIDDEN_RESULT_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "token", "password", "otp",
    "certificate_password", "cert_password", "auth_token", "access_token",
    "refresh_token", "npki_data", "private_key", "localStorage", "sessionStorage",
})

_FIXED_SAFE_RESULT_FIELDS: dict[str, Any] = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
}


def build_task(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    action: str,
    target_url: str,
    domain: str = "",
    readonly: bool = True,
    requires_user_presence: bool = False,
    timeout_seconds: int = 300,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    로컬 에이전트 실행용 안전한 task payload를 생성한다.
    민감 필드는 포함하지 않는다.
    """
    if action not in ALLOWED_TASK_ACTIONS:
        raise ValueError(f"허용되지 않은 action: {action!r}. 허용: {sorted(ALLOWED_TASK_ACTIONS)}")

    return {
        "task_id": task_id or str(uuid.uuid4()),
        "task_type": TASK_TYPE_BROWSER,
        "execution_mode": EXEC_MODE_LOCAL_PLAYWRIGHT,
        "action": action,
        "target_url": target_url,
        "domain": domain,
        "readonly": readonly,
        "requires_user_presence": requires_user_presence,
        "timeout_seconds": timeout_seconds,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "metadata": metadata or {},
    }


def build_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    ok: bool,
    status: str,
    current_url_host: str = "",
    title_hint: str = "",
    extracted_data: dict[str, Any] | None = None,
    downloaded_files: list[str] | None = None,
    message_ko: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    로컬 에이전트 실행 결과 payload를 생성한다.
    민감 필드는 항상 False/빈값으로 고정된다.
    """
    if status not in _ALL_STATUSES:
        raise ValueError(f"허용되지 않은 status: {status!r}")

    result: dict[str, Any] = {
        "task_id": task_id,
        "ok": ok,
        "execution_used": EXEC_MODE_LOCAL_PLAYWRIGHT,
        "status": status,
        "current_url_host": current_url_host,
        "title_hint": title_hint,
        "extracted_data": extracted_data or {},
        "downloaded_files": downloaded_files or [],
        "message_ko": message_ko,
        **_FIXED_SAFE_RESULT_FIELDS,
    }

    if extra:
        safe_extra = {k: v for k, v in extra.items() if k not in _FORBIDDEN_RESULT_FIELDS}
        result.update(safe_extra)

    return result


def validate_task(task: dict[str, Any]) -> list[str]:
    """
    task payload를 검증하고 위반 목록을 반환한다.
    빈 리스트 = 유효.
    """
    violations: list[str] = []

    if not task.get("task_id"):
        violations.append("task_id 누락")
    if task.get("task_type") != TASK_TYPE_BROWSER:
        violations.append(f"task_type 불일치: {task.get('task_type')!r}")
    if task.get("execution_mode") != EXEC_MODE_LOCAL_PLAYWRIGHT:
        violations.append(f"execution_mode 불일치: {task.get('execution_mode')!r}")

    action = task.get("action", "")
    if action not in ALLOWED_TASK_ACTIONS:
        violations.append(f"허용되지 않은 action: {action!r}")

    if not task.get("target_url"):
        violations.append("target_url 누락")

    for field in _FORBIDDEN_TASK_FIELDS:
        if field in task:
            violations.append(f"금지 필드 포함: {field!r}")

    return violations


def validate_result(result: dict[str, Any]) -> list[str]:
    """
    result payload를 검증하고 위반 목록을 반환한다.
    빈 리스트 = 유효.
    """
    violations: list[str] = []

    for field, expected in _FIXED_SAFE_RESULT_FIELDS.items():
        if result.get(field) is not expected:
            violations.append(f"고정 필드 값 불일치: {field!r} = {result.get(field)!r}")

    for field in _FORBIDDEN_RESULT_FIELDS:
        val = result.get(field)
        if val not in (None, False, "", [], {}):
            violations.append(f"민감 필드 노출: {field!r}")

    if result.get("status") not in _ALL_STATUSES:
        violations.append(f"허용되지 않은 status: {result.get('status')!r}")

    return violations
