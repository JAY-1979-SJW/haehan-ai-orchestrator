"""Browser Gate Approval Preflight Module.

Pre-flight approval status check for browser workflow gate decision.
Evaluates approval record state before dispatch, without executing.
Test-only implementation (no DB write, read-only approval store).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai_orchestrator.browser_tool.approval.approval_record_store import (
    build_audit_approval_context,
    get_latest_approval_status,
)

logger = logging.getLogger(__name__)


# Valid preflight_decision values
VALID_PREFLIGHT_DECISIONS = {
    "ALLOW_DRY_RUN_DISPATCH",
    "REQUIRE_APPROVAL",
    "BLOCK",
    "DENY_BY_DEFAULT",
}

# Valid block_reason values
VALID_BLOCK_REASONS = {
    "APPROVAL_REQUIRED",
    "APPROVAL_MISSING",
    "APPROVAL_NOT_FOUND",
    "APPROVAL_PENDING",
    "APPROVAL_REJECTED",
    "APPROVAL_EXPIRED",
    "APPROVAL_REVOKED",
    "SUBMIT_DENY_BY_DEFAULT",
    "TYPE_BLOCKED",
    "PRODUCTION_MODE_BLOCKED",
    "GATE_BLOCKED",
    "TENANT_CONTEXT_MISSING",
    "USER_CONTEXT_MISSING",
    "SITE_CONTEXT_MISSING",
    "UNKNOWN_OPERATION_TYPE",
}


def build_gate_approval_context(
    payload: dict,
    approval_store_path: str | Path | None = None,
) -> dict:
    """Build approval context for gate decision.

    Args:
        payload: Gate decision payload with approval_id, workflow_id, operation_type, etc.
        approval_store_path: Path to approval record JSONL store (if None, uses default)

    Returns:
        Dict with approval context (empty dict if approval not found)
    """
    approval_id = payload.get("approval_id")
    if not approval_id:
        return {}

    if approval_store_path is None:
        from ai_orchestrator.core.config import APPROVAL_RECORD_STORE_PATH

        approval_store_path = APPROVAL_RECORD_STORE_PATH

    try:
        return build_audit_approval_context(approval_id, approval_store_path)
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 - 브라우저 승인 프리플라이트 게이트 -- 기본값이 이미 BLOCK이고 approval context 조회 실패는 감사용 부가정보만 비우는 것(판정에 영향 없음), 승인 상태 조회 중 예외 발생 시에도 명시적으로 BLOCK 처리(fail-closed)
        logger.warning(f"Failed to build approval context: {e}")
        return {}


def _finish(
    result: dict,
    decision: str,
    block_reason: str,
    message_ko: str,
    *,
    audit: bool = True,
    audit_event_type: str | None = None,
    **extra: object,
) -> dict:
    """차단/요구 결과 필드를 채워 반환한다 (인라인 대입과 동일한 최종 값)."""
    result["preflight_decision"] = decision
    result["block_reason"] = block_reason
    if audit_event_type is not None:
        result["audit_event_type"] = audit_event_type
    result["message_ko"] = message_ko
    if audit:
        result["should_write_audit"] = True
    result.update(extra)
    return result


# approval_required=true 일 때 필수 context (검사 순서 고정)
_REQUIRED_CONTEXT_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("tenant_id", "TENANT_CONTEXT_MISSING", "테넌트 context 누락: approval 평가 불가"),
    ("user_id", "USER_CONTEXT_MISSING", "사용자 context 누락: approval 평가 불가"),
    ("site_id", "SITE_CONTEXT_MISSING", "사이트 context 누락: approval 평가 불가"),
)


def _check_required_context(payload: dict, result: dict) -> dict | None:
    """tenant → user → site 순으로 누락 context 를 BLOCK 한다. 모두 있으면 None."""
    for key, reason, message_ko in _REQUIRED_CONTEXT_CHECKS:
        if not payload.get(key):
            return _finish(result, "BLOCK", reason, message_ko)
    return None


def _check_blocking_policies(payload: dict, result: dict, operation_type: str) -> dict | None:
    """production_mode → 상위 gate_decision(BLOCK/DENY) → submit/type 전면 차단 (순서 고정)."""
    # Check production mode
    if payload.get("production_mode"):
        return _finish(result, "BLOCK", "PRODUCTION_MODE_BLOCKED", "production_mode=true: 실행 차단")

    # Check gate_decision from upstream policy
    gate_decision = payload.get("gate_decision", "ALLOW")
    if gate_decision == "BLOCK":
        return _finish(
            result, "BLOCK", "GATE_BLOCKED", "게이트 정책: 실행 차단", gate_decision="BLOCK"
        )

    if gate_decision == "DENY_BY_DEFAULT":
        block_reason = payload.get("block_reason", "DENY_BY_DEFAULT")
        return _finish(
            result, "DENY_BY_DEFAULT", block_reason, f"기본 차단 정책: {block_reason}",
            gate_decision="DENY_BY_DEFAULT",
        )

    # Check blocked operations regardless of approval status
    if operation_type == "submit":
        return _finish(
            result, "DENY_BY_DEFAULT", "SUBMIT_DENY_BY_DEFAULT", "submit operation: 현 단계 전면 차단"
        )

    if operation_type == "type":
        return _finish(result, "BLOCK", "TYPE_BLOCKED", "type operation: 전면 차단")
    return None


def _judge_approval_status(
    result: dict, approval_status: str, operation_type: str
) -> dict | None:
    """승인 상태별 판정. 최종 결과면 result, 계속 진행이면 None."""
    if approval_status == "PENDING":
        return _finish(
            result, "REQUIRE_APPROVAL", "APPROVAL_PENDING",
            f"approval {result['approval_id']}: 승인 대기 중",
            audit_event_type="APPROVAL_CHECKED",
        )

    if approval_status in {"REJECTED", "EXPIRED", "REVOKED"}:
        return _finish(
            result, "BLOCK", f"APPROVAL_{approval_status}",
            f"approval {result['approval_id']}: {approval_status}",
            audit_event_type="APPROVAL_CHECKED",
        )

    if approval_status == "APPROVED":
        # Approved, but still apply operation-level restrictions
        # submit and type are permanently blocked even with approval
        # Check operation_type again for safety
        if operation_type == "submit":
            return _finish(
                result, "DENY_BY_DEFAULT", "SUBMIT_DENY_BY_DEFAULT",
                "submit operation: 승인 있어도 전면 차단", approval_valid=True,
            )

        if operation_type == "type":
            return _finish(
                result, "BLOCK", "TYPE_BLOCKED",
                "type operation: 승인 있어도 전면 차단", approval_valid=True,
            )

        # Approved for other operations: allow dry-run dispatch
        if operation_type in {"read", "navigate", "open_url", "click"}:
            result["approval_valid"] = True
            result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
            result["safe_to_dispatch"] = True
            result["audit_event_type"] = "APPROVAL_CHECKED"
            result["message_ko"] = (
                f"approval {result['approval_id']}: 승인됨, {operation_type} dry-run dispatch 허용"
            )
            result["should_write_audit"] = True
            return result
    return None


def _evaluate_approval_record(
    payload: dict,
    result: dict,
    approval_store_path: str | Path | None,
    operation_type: str,
) -> dict | None:
    """approval record 조회 후 판정. 최종 결과면 result, 계속 진행이면 None (오류는 fail-closed BLOCK)."""
    if approval_store_path is None:
        from ai_orchestrator.core.config import APPROVAL_RECORD_STORE_PATH

        approval_store_path = APPROVAL_RECORD_STORE_PATH

    try:
        latest = get_latest_approval_status(result["approval_id"], approval_store_path)
        if not latest:
            return _finish(
                result, "REQUIRE_APPROVAL", "APPROVAL_NOT_FOUND",
                f"approval_id {result['approval_id']}: record 없음",
                audit_event_type="APPROVAL_CHECKED", approval_found=False,
            )

        result["approval_found"] = True
        result["approval_context"] = build_gate_approval_context(payload, approval_store_path)
        approval_status = latest.get("approval_status", "").upper()
        result["approval_status"] = approval_status

        # Check approval status
        return _judge_approval_status(result, approval_status, operation_type)

    except FileNotFoundError:
        return _finish(
            result, "REQUIRE_APPROVAL", "APPROVAL_NOT_FOUND", "approval store 없음: 승인 필요",
            audit_event_type="APPROVAL_CHECKED", approval_found=False,
        )
    except Exception as e:  # noqa: BLE001 - 브라우저 승인 프리플라이트 게이트 -- 기본값이 이미 BLOCK이고 approval context 조회 실패는 감사용 부가정보만 비우는 것(판정에 영향 없음), 승인 상태 조회 중 예외 발생 시에도 명시적으로 BLOCK 처리(fail-closed)
        logger.error(f"Error evaluating approval: {e}")
        return _finish(
            result, "BLOCK", "APPROVAL_NOT_FOUND", f"approval 평가 오류: {e!s}",
            audit_event_type="APPROVAL_CHECKED",
        )


def _allow_without_approval(result: dict, operation_type: str) -> dict | None:
    """승인 불필요 시 read/navigate/open_url/click 은 dry-run dispatch 허용. 해당 없으면 None."""
    if operation_type in {"read", "navigate", "open_url"}:
        result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
        result["safe_to_dispatch"] = True
        result["audit_event_type"] = "GATE_EVALUATED"
        result["message_ko"] = f"{operation_type} operation: dry-run dispatch 허용"
        return result

    if operation_type == "click":
        result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
        result["safe_to_dispatch"] = True
        result["audit_event_type"] = "GATE_EVALUATED"
        result["message_ko"] = "click operation (승인 불필요): dry-run dispatch 허용"
        return result
    return None


def _fallback_decision(result: dict, operation_type: str) -> dict:
    """어떤 분기도 확정하지 못했을 때의 최종 판정."""
    # Fallback: no approval required, operation is allowed
    if operation_type in {"read", "navigate", "open_url", "click"}:
        result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{operation_type} operation: 승인 불필요, dry-run dispatch 허용"
        return result

    # Fallback: default block
    result["preflight_decision"] = "BLOCK"
    result["block_reason"] = "UNKNOWN_OPERATION_TYPE"
    result["message_ko"] = f"결정 불가능: {operation_type}"
    return result


def evaluate_gate_approval_preflight(
    payload: dict,
    approval_store_path: str | Path | None = None,
) -> dict:
    """Evaluate gate approval preflight decision.

    Policy:
    1. approval_required=true + approval_id missing → REQUIRE_APPROVAL
    2. approval_required=true + approval record missing → REQUIRE_APPROVAL
    3. approval_status=PENDING → REQUIRE_APPROVAL
    4. approval_status=REJECTED/EXPIRED/REVOKED → BLOCK
    5. approval_status=APPROVED → safe_to_execute stays false, safe_to_dispatch limited
    6. submit operation + APPROVED → DENY_BY_DEFAULT
    7. type operation + APPROVED → BLOCK
    8. production_mode=true → BLOCK
    9. gate_decision=BLOCK → BLOCK
    10. gate_decision=DENY_BY_DEFAULT → DENY_BY_DEFAULT
    11. safe_to_execute always false
    12. safe_to_dispatch true only for dry-run read/open_url/click
    13. should_write_audit true when approval_required or block occurs

    Args:
        payload: Gate decision payload with:
            - workflow_run_id (required)
            - workflow_id (required)
            - action_name (required)
            - operation_type (required: read|navigate|open_url|click|type|submit)
            - approval_required (bool)
            - approval_id (optional)
            - tenant_id (required if approval_required)
            - user_id (required if approval_required)
            - site_id (required if approval_required)
            - target_domain (optional)
            - target_url_redacted (optional)
            - target_url_hash (optional)
            - gate_decision (optional: ALLOW|BLOCK|DENY_BY_DEFAULT)
            - block_reason (optional)
            - production_mode (bool)
            - dry_run (bool)
        approval_store_path: Path to approval record JSONL store

    Returns:
        Dict with preflight decision and context:
        {
            "preflight_decision": str (ALLOW_DRY_RUN_DISPATCH|REQUIRE_APPROVAL|BLOCK|DENY_BY_DEFAULT),
            "approval_status": str (PENDING|APPROVED|REJECTED|EXPIRED|REVOKED|NOT_FOUND),
            "approval_required": bool,
            "approval_id": str or None,
            "approval_found": bool,
            "approval_valid": bool,
            "approval_context": dict,
            "gate_decision": str (ALLOW|BLOCK|DENY_BY_DEFAULT),
            "block_reason": str or None,
            "safe_to_dispatch": bool,
            "safe_to_execute": bool,
            "should_write_audit": bool,
            "audit_event_type": str (GATE_EVALUATED|APPROVAL_CHECKED|DISPATCH_BLOCKED|etc),
            "message_ko": str,
        }
    """
    result = {
        "preflight_decision": "BLOCK",
        "approval_status": "NOT_FOUND",
        "approval_required": payload.get("approval_required", False),
        "approval_id": payload.get("approval_id"),
        "approval_found": False,
        "approval_valid": False,
        "approval_context": {},
        "gate_decision": payload.get("gate_decision", "ALLOW"),
        "block_reason": None,
        "safe_to_dispatch": False,
        "safe_to_execute": False,  # Always false, policy enforcement
        "should_write_audit": False,
        "audit_event_type": "GATE_EVALUATED",
        "message_ko": "",
    }

    # Validate required context fields
    if result["approval_required"]:
        context_missing = _check_required_context(payload, result)
        if context_missing is not None:
            return context_missing

    # Check operation_type validity
    operation_type = payload.get("operation_type", "").lower()
    valid_ops = {"read", "navigate", "open_url", "click", "type", "submit"}
    if operation_type not in valid_ops:
        return _finish(
            result, "BLOCK", "UNKNOWN_OPERATION_TYPE", f"알 수 없는 operation_type: {operation_type}", audit=False
        )

    # production / upstream gate_decision / submit·type 전면 차단
    blocked = _check_blocking_policies(payload, result, operation_type)
    if blocked is not None:
        return blocked

    # If approval not required, allow dry-run dispatch
    if not result["approval_required"]:
        allowed = _allow_without_approval(result, operation_type)
        if allowed is not None:
            return allowed

    if result["approval_required"]:
        # Approval required: check if approval_id is provided
        if not result["approval_id"]:
            return _finish(
                result, "REQUIRE_APPROVAL", "APPROVAL_MISSING", "approval_id 누락: 승인 필요",
                audit_event_type="APPROVAL_CHECKED",
            )

        # Approval required: fetch approval record
        record_outcome = _evaluate_approval_record(
            payload, result, approval_store_path, operation_type
        )
        if record_outcome is not None:
            return record_outcome

    return _fallback_decision(result, operation_type)


def validate_gate_approval_result(result: dict) -> list[str]:
    """Validate gate approval preflight result.

    Args:
        result: Result dict from evaluate_gate_approval_preflight()

    Returns:
        List of error messages (empty list = valid)
    """
    errors = []

    # Required fields
    if not result.get("preflight_decision"):
        errors.append("preflight_decision is required")
    elif result["preflight_decision"] not in VALID_PREFLIGHT_DECISIONS:
        errors.append(f"preflight_decision must be one of {VALID_PREFLIGHT_DECISIONS}")

    if "approval_status" not in result:
        errors.append("approval_status is required")

    if "safe_to_execute" not in result:
        errors.append("safe_to_execute is required")

    # Policy enforcement: safe_to_execute must always be false
    if result.get("safe_to_execute"):
        errors.append("safe_to_execute must be false")

    # Policy enforcement: block_reason should be present if BLOCK/DENY_BY_DEFAULT
    decision = result.get("preflight_decision")
    if decision in {"BLOCK", "DENY_BY_DEFAULT"}:
        if not result.get("block_reason"):
            errors.append(f"{decision} decision requires block_reason")
        elif result["block_reason"] not in VALID_BLOCK_REASONS:
            errors.append(f"block_reason must be one of {VALID_BLOCK_REASONS}, got {result['block_reason']}")

    return errors
