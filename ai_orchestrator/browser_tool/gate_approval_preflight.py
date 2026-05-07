"""Browser Gate Approval Preflight Module.

Pre-flight approval status check for browser workflow gate decision.
Evaluates approval record state before dispatch, without executing.
Test-only implementation (no DB write, read-only approval store).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from .approval_record_store import (
    get_latest_approval_status,
    build_audit_approval_context,
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
        from ai_orchestrator.config import APPROVAL_RECORD_STORE_PATH
        approval_store_path = APPROVAL_RECORD_STORE_PATH

    try:
        return build_audit_approval_context(approval_id, approval_store_path)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"Failed to build approval context: {e}")
        return {}


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
        if not payload.get("tenant_id"):
            result["block_reason"] = "TENANT_CONTEXT_MISSING"
            result["preflight_decision"] = "BLOCK"
            result["message_ko"] = "테넌트 context 누락: approval 평가 불가"
            result["should_write_audit"] = True
            return result

        if not payload.get("user_id"):
            result["block_reason"] = "USER_CONTEXT_MISSING"
            result["preflight_decision"] = "BLOCK"
            result["message_ko"] = "사용자 context 누락: approval 평가 불가"
            result["should_write_audit"] = True
            return result

        if not payload.get("site_id"):
            result["block_reason"] = "SITE_CONTEXT_MISSING"
            result["preflight_decision"] = "BLOCK"
            result["message_ko"] = "사이트 context 누락: approval 평가 불가"
            result["should_write_audit"] = True
            return result

    # Check operation_type validity
    operation_type = payload.get("operation_type", "").lower()
    valid_ops = {"read", "navigate", "open_url", "click", "type", "submit"}
    if operation_type not in valid_ops:
        result["block_reason"] = "UNKNOWN_OPERATION_TYPE"
        result["preflight_decision"] = "BLOCK"
        result["message_ko"] = f"알 수 없는 operation_type: {operation_type}"
        return result

    # Check production mode
    if payload.get("production_mode"):
        result["preflight_decision"] = "BLOCK"
        result["block_reason"] = "PRODUCTION_MODE_BLOCKED"
        result["message_ko"] = "production_mode=true: 실행 차단"
        result["should_write_audit"] = True
        return result

    # Check gate_decision from upstream policy
    gate_decision = payload.get("gate_decision", "ALLOW")
    if gate_decision == "BLOCK":
        result["gate_decision"] = "BLOCK"
        result["preflight_decision"] = "BLOCK"
        result["block_reason"] = "GATE_BLOCKED"
        result["message_ko"] = "게이트 정책: 실행 차단"
        result["should_write_audit"] = True
        return result

    if gate_decision == "DENY_BY_DEFAULT":
        result["gate_decision"] = "DENY_BY_DEFAULT"
        result["preflight_decision"] = "DENY_BY_DEFAULT"
        result["block_reason"] = payload.get("block_reason", "DENY_BY_DEFAULT")
        result["message_ko"] = f"기본 차단 정책: {result['block_reason']}"
        result["should_write_audit"] = True
        return result

    # Check blocked operations regardless of approval status
    if operation_type == "submit":
        result["preflight_decision"] = "DENY_BY_DEFAULT"
        result["block_reason"] = "SUBMIT_DENY_BY_DEFAULT"
        result["message_ko"] = "submit operation: 현 단계 전면 차단"
        result["should_write_audit"] = True
        return result

    if operation_type == "type":
        result["preflight_decision"] = "BLOCK"
        result["block_reason"] = "TYPE_BLOCKED"
        result["message_ko"] = "type operation: 전면 차단"
        result["should_write_audit"] = True
        return result

    # If approval not required, allow dry-run dispatch
    if not result["approval_required"]:
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

    # Approval required: check if approval_id is provided
    if result["approval_required"] and not result["approval_id"]:
        result["preflight_decision"] = "REQUIRE_APPROVAL"
        result["block_reason"] = "APPROVAL_MISSING"
        result["audit_event_type"] = "APPROVAL_CHECKED"
        result["message_ko"] = "approval_id 누락: 승인 필요"
        result["should_write_audit"] = True
        return result

    # Approval required: fetch approval record
    if result["approval_required"] and result["approval_id"]:
        if approval_store_path is None:
            from ai_orchestrator.config import APPROVAL_RECORD_STORE_PATH
            approval_store_path = APPROVAL_RECORD_STORE_PATH

        try:
            latest = get_latest_approval_status(result["approval_id"], approval_store_path)
            if not latest:
                result["preflight_decision"] = "REQUIRE_APPROVAL"
                result["block_reason"] = "APPROVAL_NOT_FOUND"
                result["approval_found"] = False
                result["audit_event_type"] = "APPROVAL_CHECKED"
                result["message_ko"] = f"approval_id {result['approval_id']}: record 없음"
                result["should_write_audit"] = True
                return result

            result["approval_found"] = True
            result["approval_context"] = build_gate_approval_context(payload, approval_store_path)
            approval_status = latest.get("approval_status", "").upper()
            result["approval_status"] = approval_status

            # Check approval status
            if approval_status == "PENDING":
                result["preflight_decision"] = "REQUIRE_APPROVAL"
                result["block_reason"] = "APPROVAL_PENDING"
                result["audit_event_type"] = "APPROVAL_CHECKED"
                result["message_ko"] = f"approval {result['approval_id']}: 승인 대기 중"
                result["should_write_audit"] = True
                return result

            if approval_status in {"REJECTED", "EXPIRED", "REVOKED"}:
                result["preflight_decision"] = "BLOCK"
                result["block_reason"] = f"APPROVAL_{approval_status}"
                result["audit_event_type"] = "APPROVAL_CHECKED"
                result["message_ko"] = f"approval {result['approval_id']}: {approval_status}"
                result["should_write_audit"] = True
                return result

            if approval_status == "APPROVED":
                # Approved, but still apply operation-level restrictions
                # submit and type are permanently blocked even with approval
                # Check operation_type again for safety
                if operation_type == "submit":
                    result["preflight_decision"] = "DENY_BY_DEFAULT"
                    result["block_reason"] = "SUBMIT_DENY_BY_DEFAULT"
                    result["approval_valid"] = True
                    result["message_ko"] = "submit operation: 승인 있어도 전면 차단"
                    result["should_write_audit"] = True
                    return result

                if operation_type == "type":
                    result["preflight_decision"] = "BLOCK"
                    result["block_reason"] = "TYPE_BLOCKED"
                    result["approval_valid"] = True
                    result["message_ko"] = "type operation: 승인 있어도 전면 차단"
                    result["should_write_audit"] = True
                    return result

                # Approved for other operations: allow dry-run dispatch
                if operation_type in {"read", "navigate", "open_url", "click"}:
                    result["approval_valid"] = True
                    result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
                    result["safe_to_dispatch"] = True
                    result["audit_event_type"] = "APPROVAL_CHECKED"
                    result["message_ko"] = f"approval {result['approval_id']}: 승인됨, {operation_type} dry-run dispatch 허용"
                    result["should_write_audit"] = True
                    return result

        except FileNotFoundError:
            result["preflight_decision"] = "REQUIRE_APPROVAL"
            result["block_reason"] = "APPROVAL_NOT_FOUND"
            result["approval_found"] = False
            result["audit_event_type"] = "APPROVAL_CHECKED"
            result["message_ko"] = "approval store 없음: 승인 필요"
            result["should_write_audit"] = True
            return result
        except Exception as e:
            logger.error(f"Error evaluating approval: {e}")
            result["preflight_decision"] = "BLOCK"
            result["block_reason"] = "APPROVAL_NOT_FOUND"
            result["audit_event_type"] = "APPROVAL_CHECKED"
            result["message_ko"] = f"approval 평가 오류: {str(e)}"
            result["should_write_audit"] = True
            return result

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
