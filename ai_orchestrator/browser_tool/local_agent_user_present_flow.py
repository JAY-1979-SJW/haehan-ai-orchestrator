"""
로컬 Agent 사용자 직접 인증 흐름 모듈

AI는 민감정보(비밀번호, OTP, 인증서 비밀번호)를 입력/저장/전송하지 않는다.
사용자가 직접 인증해야 하는 구간은 USER_PRESENT_REQUIRED 상태로 대기한다.
"""

from __future__ import annotations

from typing import Any

# 실행 위치 코드
EXEC_LOC_SERVER_READONLY = "SERVER_BROWSER_READONLY_OK"
EXEC_LOC_LOCAL_AGENT = "LOCAL_AGENT_REQUIRED"
EXEC_LOC_USER_PRESENT = "USER_PRESENT_REQUIRED"
EXEC_LOC_API = "API_REQUIRED"
EXEC_LOC_BLOCKED = "AUTOMATION_BLOCKED"

# 로컬 Agent 결정 코드
DECISION_REQUIRE_USER_PRESENT = "REQUIRE_USER_PRESENT"
DECISION_REQUIRE_LOCAL_AGENT = "REQUIRE_LOCAL_AGENT"
DECISION_REQUIRE_API = "REQUIRE_API_CONNECTOR"
DECISION_READONLY = "READONLY_ALLOWED"
DECISION_BLOCK = "BLOCK"

# 사용자 화면에 절대 노출하면 안 되는 필드
_USER_FORBIDDEN_KEYS = frozenset(
    {
        "internal_policy",
        "full_policy",
        "action_metadata",
        "raw_validation_errors",
        "system_trace",
        "detailed_audit_event",
        "raw_audit_log",
        "audit_raw",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "session",
        "secret",
        "api_key",
        "oauth_token",
        "password",
        "certificate_password",
        "financial_certificate_password",
        "otp",
        "security_card",
        "other_tenant_data",
        "other_user_tasks",
        "other_user_workflow_run_id",
        "server_path",
        "workflow_id",
        "tenant_id",
        "user_id",
        "site_id",
        "full_preflight_policy",
        "action_registry_raw",
        "cross_tenant_data",
    }
)

# 관리자 화면에도 노출하면 안 되는 필드 (raw sensitive)
_ADMIN_FORBIDDEN_KEYS = frozenset(
    {
        "password",
        "certificate_password",
        "financial_certificate_password",
        "otp",
        "security_card",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "session",
        "secret",
        "api_key",
        "oauth_token",
        "raw_audit_log",
        "system_trace",
        "raw_validation_errors",
    }
)

# AI 입력이 차단되는 민감항목
_SENSITIVE_INPUT_TYPES = (
    "password",
    "otp",
    "certificate_password",
    "financial_certificate_password",
    "security_card",
    "captcha_answer",
)

# 사이트 카테고리별 기본 실행 위치 매핑
_SITE_CATEGORY_DEFAULT_LOCATION: dict[str, str] = {
    "bank": EXEC_LOC_USER_PRESENT,
    "card": EXEC_LOC_USER_PRESENT,
    "tax": EXEC_LOC_USER_PRESENT,
    "government": EXEC_LOC_LOCAL_AGENT,
    "insurance": EXEC_LOC_LOCAL_AGENT,
    "procurement": EXEC_LOC_SERVER_READONLY,
    "cloud_service": EXEC_LOC_API,
}

# 사용자 안내 문구 (한글)
_USER_MESSAGES_KO = {
    DECISION_REQUIRE_USER_PRESENT: (
        "이 단계는 공동인증서/금융인증서/OTP/비밀번호가 필요합니다. "
        "AI는 민감정보를 입력하거나 볼 수 없습니다. "
        "사용자가 직접 인증을 완료한 뒤 인증 완료 버튼을 눌러주세요. "
        "제출/결제/이체는 자동 실행되지 않습니다. "
        "현재 화면에는 사용자 본인 작업 정보만 표시됩니다."
    ),
    DECISION_REQUIRE_LOCAL_AGENT: (
        "이 작업은 로컬 Agent에서 처리됩니다. "
        "사용자 직접 인증이 필요한 경우 별도 안내가 표시됩니다. "
        "현재 화면에는 사용자 본인 작업 정보만 표시됩니다."
    ),
    DECISION_REQUIRE_API: "이 작업은 API를 통해 처리됩니다.",
    DECISION_READONLY: "이 작업은 읽기 전용으로 처리됩니다.",
    DECISION_BLOCK: ("이 작업은 자동화가 차단되었습니다. CAPTCHA 또는 키보드 보안 등의 이유로 자동 실행이 불가합니다."),
}


def _determine_execution_location(payload: dict[str, Any]) -> str:
    """사이트 특성에 따라 실행 위치를 결정한다."""
    if payload.get("requires_captcha"):
        return EXEC_LOC_BLOCKED

    if payload.get("api_required"):
        return EXEC_LOC_API

    site_category = payload.get("site_category", "")
    if site_category == "cloud_service":
        return EXEC_LOC_API

    if payload.get("requires_certificate") or payload.get("requires_financial_certificate"):
        return EXEC_LOC_USER_PRESENT

    if payload.get("requires_otp"):
        return EXEC_LOC_USER_PRESENT

    if payload.get("requires_password") and site_category in ("bank", "card", "tax"):
        return EXEC_LOC_USER_PRESENT

    if payload.get("requires_security_plugin"):
        return EXEC_LOC_USER_PRESENT

    return _SITE_CATEGORY_DEFAULT_LOCATION.get(site_category, EXEC_LOC_LOCAL_AGENT)


def _determine_local_agent_decision(execution_location: str) -> str:
    _map = {
        EXEC_LOC_USER_PRESENT: DECISION_REQUIRE_USER_PRESENT,
        EXEC_LOC_LOCAL_AGENT: DECISION_REQUIRE_LOCAL_AGENT,
        EXEC_LOC_API: DECISION_REQUIRE_API,
        EXEC_LOC_SERVER_READONLY: DECISION_READONLY,
        EXEC_LOC_BLOCKED: DECISION_BLOCK,
    }
    return _map.get(execution_location, DECISION_BLOCK)


def _build_sensitive_inputs_blocked(payload: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if payload.get("requires_password"):
        blocked.append("password")
    if payload.get("requires_otp"):
        blocked.append("otp")
    if payload.get("requires_certificate"):
        blocked.append("certificate_password")
    if payload.get("requires_financial_certificate"):
        blocked.append("financial_certificate_password")
    if payload.get("requires_captcha"):
        blocked.append("captcha_answer")
    return blocked


def _build_allowed_next_actions(decision: str) -> list[str]:
    if decision == DECISION_REQUIRE_USER_PRESENT:
        return ["open_site", "readonly_status_check", "wait_for_user", "accept_user_confirmed", "accept_user_cancelled"]
    if decision == DECISION_REQUIRE_LOCAL_AGENT:
        return ["open_site", "readonly_status_check", "wait_for_user"]
    if decision == DECISION_REQUIRE_API:
        return ["api_call"]
    if decision == DECISION_READONLY:
        return ["open_site", "readonly_scrape", "readonly_status_check"]
    return []


def _build_blocked_next_actions(payload: dict[str, Any]) -> list[str]:
    blocked = [
        "type",
        "submit",
        "fill_password",
        "fill_otp",
        "sign_certificate",
        "extract_cookie",
        "extract_session",
        "extract_token",
        "extract_localStorage",
    ]
    if payload.get("requires_certificate") or payload.get("requires_financial_certificate"):
        blocked.append("fill_certificate_password")
        blocked.append("auto_sign_certificate")
    return blocked


def build_user_present_task(payload: dict[str, Any]) -> dict[str, Any]:
    """사용자 직접 인증 작업 객체를 생성한다."""
    execution_location = _determine_execution_location(payload)
    decision = _determine_local_agent_decision(execution_location)

    task: dict[str, Any] = {
        "workflow_run_id": payload.get("workflow_run_id"),
        "execution_location": execution_location,
        "local_agent_decision": decision,
        "user_present_required": execution_location in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT),
        "local_agent_required": execution_location in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT),
        "api_required": execution_location == EXEC_LOC_API,
        "blocked_for_ai_input": bool(_build_sensitive_inputs_blocked(payload)),
        "sensitive_inputs_blocked": _build_sensitive_inputs_blocked(payload),
        "allowed_next_actions": _build_allowed_next_actions(decision),
        "blocked_next_actions": _build_blocked_next_actions(payload),
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "audit_required": True,
        "block_reason": "CAPTCHA_PRESENT" if payload.get("requires_captcha") else None,
        "state": "WAITING_FOR_USER" if execution_location == EXEC_LOC_USER_PRESENT else "PENDING",
        "user_message_ko": _USER_MESSAGES_KO.get(decision, ""),
        "_raw_payload": payload,
    }
    return task


def evaluate_user_present_requirement(payload: dict[str, Any]) -> dict[str, Any]:
    """사용자 직접 인증 필요 여부를 평가한다."""
    execution_location = _determine_execution_location(payload)
    return {
        "user_present_required": execution_location == EXEC_LOC_USER_PRESENT,
        "local_agent_required": execution_location in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT),
        "api_required": execution_location == EXEC_LOC_API,
        "execution_location": execution_location,
        "sensitive_inputs_blocked": _build_sensitive_inputs_blocked(payload),
    }


def build_local_agent_instruction(payload: dict[str, Any]) -> dict[str, Any]:
    """로컬 Agent에 전달할 지시 객체를 생성한다. 민감정보를 포함하지 않는다."""
    execution_location = _determine_execution_location(payload)
    decision = _determine_local_agent_decision(execution_location)
    return {
        "workflow_run_id": payload.get("workflow_run_id"),
        "site_category": payload.get("site_category"),
        "target_domain": payload.get("target_domain"),
        "target_url_redacted": payload.get("target_url_redacted"),
        "operation_type": payload.get("operation_type"),
        "auth_method": payload.get("auth_method"),
        "execution_location": execution_location,
        "local_agent_decision": decision,
        "user_present_required": execution_location in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT),
        "allowed_next_actions": _build_allowed_next_actions(decision),
        "blocked_next_actions": _build_blocked_next_actions(payload),
        "sensitive_inputs_blocked": _build_sensitive_inputs_blocked(payload),
        "safe_to_execute": False,
        "user_message_ko": _USER_MESSAGES_KO.get(decision, ""),
    }


def build_user_visible_status(payload: dict[str, Any]) -> dict[str, Any]:
    """사용자 로컬 웹에 표시할 상태 객체를 생성한다. 민감정보를 포함하지 않는다."""
    execution_location = _determine_execution_location(payload)
    decision = _determine_local_agent_decision(execution_location)
    return {
        "task_name": payload.get("operation_type"),
        "site_name_redacted": payload.get("target_domain"),
        "site_category": payload.get("site_category"),
        "current_step": execution_location,
        "auth_method_guide": payload.get("auth_method"),
        "user_present_required": execution_location in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT),
        "state": "WAITING_FOR_USER" if execution_location == EXEC_LOC_USER_PRESENT else "PENDING",
        "user_message_ko": _USER_MESSAGES_KO.get(decision, ""),
        "available_actions": ["confirm_auth_completed", "cancel"],
        "workflow_run_id": payload.get("workflow_run_id"),
    }


def build_admin_visible_status(payload: dict[str, Any]) -> dict[str, Any]:
    """관리자 UI에 표시할 상태 객체를 생성한다. raw sensitive 필드를 제외한다."""
    execution_location = _determine_execution_location(payload)
    decision = _determine_local_agent_decision(execution_location)
    return {
        "workflow_id": payload.get("workflow_id"),
        "workflow_run_id": payload.get("workflow_run_id"),
        "tenant_id": payload.get("tenant_id"),
        "user_id": payload.get("user_id"),
        "site_id": payload.get("site_id"),
        "site_category": payload.get("site_category"),
        "execution_location": execution_location,
        "local_agent_decision": decision,
        "approval_status": payload.get("approval_status", "PENDING"),
        "block_reason": "CAPTCHA_PRESENT" if payload.get("requires_captcha") else None,
        "user_present_required": execution_location in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT),
        "safe_to_execute": False,
        "preflight_summary": payload.get("preflight_summary"),
    }


def sanitize_user_visible_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """사용자 화면에 전달되는 payload에서 금지 필드를 제거한다."""
    return {k: v for k, v in payload.items() if k not in _USER_FORBIDDEN_KEYS}


def sanitize_admin_visible_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """관리자 화면에 전달되는 payload에서 raw sensitive 필드를 제거한다."""
    return {k: v for k, v in payload.items() if k not in _ADMIN_FORBIDDEN_KEYS}


def mark_user_present_waiting(task: dict[str, Any]) -> dict[str, Any]:
    """작업 상태를 WAITING_FOR_USER로 전환한다."""
    return {**task, "state": "WAITING_FOR_USER"}


def mark_user_confirmed_auth(task: dict[str, Any]) -> dict[str, Any]:
    """사용자가 인증 완료 버튼을 클릭한 상태로 전환한다."""
    return {**task, "state": "USER_CONFIRMED"}


def mark_user_cancelled(task: dict[str, Any]) -> dict[str, Any]:
    """사용자가 중단 버튼을 클릭한 상태로 전환한다."""
    return {**task, "state": "CANCELLED"}


def validate_user_present_flow_result(result: dict[str, Any]) -> list[str]:
    """결과 객체의 필수 필드와 정책 준수를 검증한다."""
    errors: list[str] = []

    required_fields = [
        "local_agent_decision",
        "execution_location",
        "user_present_required",
        "local_agent_required",
        "api_required",
        "blocked_for_ai_input",
        "allowed_next_actions",
        "blocked_next_actions",
        "user_message_ko",
        "safe_to_dispatch",
        "safe_to_execute",
        "audit_required",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    blocked_actions = result.get("blocked_next_actions", [])
    if "type" not in blocked_actions and "submit" not in blocked_actions:
        errors.append("blocked_next_actions에 type/submit이 포함되어야 한다")

    valid_decisions = {
        DECISION_REQUIRE_USER_PRESENT,
        DECISION_REQUIRE_LOCAL_AGENT,
        DECISION_REQUIRE_API,
        DECISION_READONLY,
        DECISION_BLOCK,
    }
    decision = result.get("local_agent_decision")
    if decision not in valid_decisions:
        errors.append(f"유효하지 않은 local_agent_decision: {decision}")

    return errors
