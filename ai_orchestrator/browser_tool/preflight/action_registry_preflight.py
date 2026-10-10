"""Browser Action Registry Preflight Module.

Pre-flight action registry check for browser workflow execution readiness.
Evaluates action metadata, operation type, approval status, and gates
before dispatch without executing.
Test-only implementation (read-only, no execution, no DB write).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai_orchestrator.browser_tool.preflight.agent_action_registry import get_meta, is_known_action
from ai_orchestrator.browser_tool.preflight.gate_approval_preflight import evaluate_gate_approval_preflight

logger = logging.getLogger(__name__)


# Browser action policy defaults
BROWSER_ACTION_POLICIES = {
    "browser.inspect": {
        "operation_type": "read",
        "risk_level": "low",
        "approval_required": False,
        "audit_required": False,
        "gate_required": False,
        "allowlist_required": False,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.plan_click": {
        "operation_type": "read",
        "risk_level": "low",
        "approval_required": False,
        "audit_required": False,
        "gate_required": False,
        "allowlist_required": False,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.plan_open_url": {
        "operation_type": "navigate",
        "risk_level": "low",
        "approval_required": False,
        "audit_required": False,
        "gate_required": False,
        "allowlist_required": True,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.open_url_controlled": {
        "operation_type": "open_url",
        "risk_level": "medium",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": True,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.execute_click": {
        "operation_type": "click",
        "risk_level": "medium",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": True,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.execute_type": {
        "operation_type": "type",
        "risk_level": "high",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": False,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": False,
        "safe_to_execute_allowed": False,
        "blocked_by_default": True,
        "block_reason": "TYPE_BLOCKED",
    },
    "browser.open_click_close_controlled": {
        "operation_type": "click",
        "risk_level": "medium",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": True,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.open_type_close_controlled": {
        "operation_type": "type",
        "risk_level": "critical",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": False,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": False,
        "safe_to_execute_allowed": False,
        "blocked_by_default": True,
        "block_reason": "SUBMIT_DENY_BY_DEFAULT",
    },
    # ── Unified Execution Router actions ──────────────────────────────────────
    "browser.unified.execute": {
        "operation_type": "navigate",
        "risk_level": "medium",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": True,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
    "browser.unified.classify": {
        "operation_type": "read",
        "risk_level": "low",
        "approval_required": False,
        "audit_required": False,
        "gate_required": False,
        "allowlist_required": False,
        "production_allowed": True,
        "dry_run_only": False,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": True,
        "blocked_by_default": False,
    },
    "browser.unified.fallback_decide": {
        "operation_type": "read",
        "risk_level": "low",
        "approval_required": False,
        "audit_required": True,
        "gate_required": False,
        "allowlist_required": False,
        "production_allowed": True,
        "dry_run_only": False,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": True,
        "blocked_by_default": False,
    },
    "browser.unified.local_handoff": {
        "operation_type": "navigate",
        "risk_level": "medium",
        "approval_required": True,
        "audit_required": True,
        "gate_required": True,
        "allowlist_required": True,
        "production_allowed": False,
        "dry_run_only": True,
        "safe_to_dispatch_allowed": True,
        "safe_to_execute_allowed": False,
        "blocked_by_default": False,
    },
}


def get_browser_action_policy(action_name: str) -> dict:
    """Get browser action policy from defaults or registry.

    Args:
        action_name: Action name (e.g., "browser.inspect")

    Returns:
        Policy dict with operation_type, approval_required, etc.
        Returns empty dict if action not known.
    """
    # First check defaults (planned actions)
    if action_name in BROWSER_ACTION_POLICIES:
        return BROWSER_ACTION_POLICIES[action_name]

    # Then check agent registry
    meta = get_meta(action_name)
    if meta:
        return {
            "operation_type": _infer_operation_type(action_name),
            "risk_level": meta.risk_level,
            "approval_required": meta.requires_approval,
            "audit_required": False,  # Not in ActionMeta yet
            "gate_required": False,
            "allowlist_required": False,
            "production_allowed": False,
            "dry_run_only": True,
            "safe_to_dispatch_allowed": not meta.requires_approval,
            "safe_to_execute_allowed": False,
            "blocked_by_default": False,
        }

    return {}


def _infer_operation_type(action_name: str) -> str:
    """Infer operation_type from action name."""
    if "submit" in action_name.lower():
        return "submit"
    if "type" in action_name.lower() and "click" not in action_name.lower():
        return "type"
    if "click" in action_name.lower():
        return "click"
    if "open_url" in action_name.lower() or "navigate" in action_name.lower():
        return "navigate"
    return "read"


def build_action_preflight_context(payload: dict) -> dict:
    """Build action preflight context.

    Args:
        payload: Action request payload with action_name, operation_type, etc.

    Returns:
        Dict with action context and registry policy
    """
    action_name = payload.get("action_name", "")
    action_known = is_known_action(action_name) or action_name in BROWSER_ACTION_POLICIES

    policy = get_browser_action_policy(action_name) if action_known else {}

    return {
        "action_name": action_name,
        "action_known": action_known,
        "operation_type": policy.get("operation_type", "unknown"),
        "registry_policy": policy,
    }


_DRY_RUN_DISPATCH_OPERATIONS = {"read", "navigate", "open_url", "click"}

# gate 판정 → (block_reason 기본값, 메시지 접미사)
_GATE_DECISION_BLOCKS: dict[str, tuple[str, str]] = {
    "BLOCK": ("GATE_BLOCKED", "gate 정책 차단"),
    "DENY_BY_DEFAULT": ("DENY_BY_DEFAULT", "기본 차단"),
    "REQUIRE_APPROVAL": ("APPROVAL_REQUIRED", "승인 필요"),
}


# operation_type → (preflight_decision, block_reason, 메시지 접미사)
_OPERATION_TYPE_DENIALS: dict[str, tuple[str, str, str]] = {
    "submit": ("DENY_BY_DEFAULT", "SUBMIT_DENY_BY_DEFAULT", "submit 전면 차단"),
    "type": ("BLOCK", "TYPE_BLOCKED", "type 전면 차단"),
}


def _finish_blocked(
    result: dict, decision: str, block_reason: str, message_ko: str, audit: bool = True
) -> dict:
    """차단/거부 결과 필드를 채워 반환한다."""
    result["preflight_decision"] = decision
    result["block_reason"] = block_reason
    result["message_ko"] = message_ko
    if audit:
        result["should_write_audit"] = True
    return result


def _evaluate_approval_gate(
    result: dict,
    payload: dict,
    approval_store_path: str | Path | None,
    action_name: str,
    operation_type: str,
) -> dict | None:
    """승인 필요 action 의 gate preflight 평가. 최종 결과면 result, 계속 진행이면 None."""
    gate_result = evaluate_gate_approval_preflight(payload, approval_store_path)
    result["gate_preflight_decision"] = gate_result.get("preflight_decision", "BLOCK")

    # Extract approval status
    approval_status = gate_result.get("approval_status", "NOT_FOUND")
    result["approval_status"] = approval_status

    gate_decision = gate_result.get("preflight_decision", "BLOCK")

    # Check gate decision
    if gate_decision in _GATE_DECISION_BLOCKS:
        default_reason, message_suffix = _GATE_DECISION_BLOCKS[gate_decision]
        return _finish_blocked(
            result,
            gate_decision,
            gate_result.get("block_reason", default_reason),
            f"{action_name}: {message_suffix}",
        )

    # Gate approved
    if gate_decision == "ALLOW_DRY_RUN_DISPATCH" and operation_type in _DRY_RUN_DISPATCH_OPERATIONS:
        result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{action_name}: 승인됨, dry-run dispatch 허용"
        result["should_write_audit"] = True
        return result

    return None


def evaluate_action_registry_preflight(
    payload: dict,
    approval_store_path: str | Path | None = None,
) -> dict:
    """Evaluate action registry preflight decision.

    Args:
        payload: Action request with:
            - action_name (required)
            - workflow_run_id, workflow_id, operation_type (context)
            - approval_required, approval_id (approval context)
            - production_mode, dry_run (execution context)
            - tenant_id, user_id, site_id (required if approval_required)
        approval_store_path: Path to approval store

    Returns:
        Dict with action preflight decision:
        {
            "action_name": str,
            "action_known": bool,
            "action_allowed_by_registry": bool,
            "registry_policy": dict,
            "gate_preflight_decision": str,
            "approval_status": str,
            "approval_required": bool,
            "audit_required": bool,
            "gate_required": bool,
            "allowlist_required": bool,
            "production_allowed": bool,
            "dry_run_only": bool,
            "preflight_decision": str (ALLOW_DRY_RUN_DISPATCH|REQUIRE_APPROVAL|BLOCK|DENY_BY_DEFAULT|UNKNOWN_ACTION),
            "block_reason": str or None,
            "safe_to_dispatch": bool,
            "safe_to_execute": bool,
            "should_write_audit": bool,
            "message_ko": str,
        }
    """
    result = {
        "action_name": payload.get("action_name", ""),
        "action_known": False,
        "action_allowed_by_registry": False,
        "registry_policy": {},
        "gate_preflight_decision": "ALLOW",
        "approval_status": "NOT_FOUND",
        "approval_required": False,
        "audit_required": False,
        "gate_required": False,
        "allowlist_required": False,
        "production_allowed": False,
        "dry_run_only": True,
        "preflight_decision": "BLOCK",
        "block_reason": None,
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "should_write_audit": False,
        "message_ko": "",
    }

    action_name = result["action_name"]

    # Check if action is known
    if not action_name:
        result["block_reason"] = "ACTION_UNKNOWN"
        result["message_ko"] = "action_name 누락"
        return result

    policy = get_browser_action_policy(action_name)
    if not policy:
        result["preflight_decision"] = "UNKNOWN_ACTION"
        result["block_reason"] = "ACTION_UNKNOWN"
        result["message_ko"] = f"알 수 없는 action: {action_name}"
        return result

    result["action_known"] = True
    result["registry_policy"] = policy
    result["action_allowed_by_registry"] = True
    result["approval_required"] = policy.get("approval_required", False)
    result["audit_required"] = policy.get("audit_required", False)
    result["gate_required"] = policy.get("gate_required", False)
    result["allowlist_required"] = policy.get("allowlist_required", False)
    result["production_allowed"] = policy.get("production_allowed", False)
    result["dry_run_only"] = policy.get("dry_run_only", True)

    operation_type = policy.get("operation_type", "unknown").lower()

    # Check production mode
    if payload.get("production_mode"):
        return _finish_blocked(
            result, "BLOCK", "PRODUCTION_MODE_BLOCKED", f"{action_name}: production mode 차단"
        )

    # Operation type specific checks (priority before blocked_by_default)
    if operation_type in _OPERATION_TYPE_DENIALS:
        decision, reason, message_suffix = _OPERATION_TYPE_DENIALS[operation_type]
        return _finish_blocked(result, decision, reason, f"{action_name}: {message_suffix}")

    # Check blocked by default
    if policy.get("blocked_by_default"):
        block_reason = policy.get("block_reason", "ACTION_BLOCKED")
        return _finish_blocked(result, "DENY_BY_DEFAULT", block_reason, f"{action_name}: {block_reason}")

    # If no approval required, allow dry-run dispatch
    if not result["approval_required"] and operation_type in _DRY_RUN_DISPATCH_OPERATIONS:
        result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{action_name}: dry-run dispatch 허용"
        return result

    # Approval required: evaluate gate preflight
    if result["approval_required"]:
        gate_outcome = _evaluate_approval_gate(
            result, payload, approval_store_path, action_name, operation_type
        )
        if gate_outcome is not None:
            return gate_outcome

    # Default: allow if all checks passed
    if operation_type in _DRY_RUN_DISPATCH_OPERATIONS:
        result["preflight_decision"] = "ALLOW_DRY_RUN_DISPATCH"
        result["safe_to_dispatch"] = True
        result["message_ko"] = f"{action_name}: dry-run dispatch 허용"
        return result

    # Fallback: block
    return _finish_blocked(result, "BLOCK", "ACTION_NOT_ALLOWED", f"{action_name}: 실행 불가", audit=False)


def validate_action_preflight_result(result: dict) -> list[str]:
    """Validate action preflight result.

    Args:
        result: Result from evaluate_action_registry_preflight()

    Returns:
        List of error messages (empty = valid)
    """
    errors = []

    # Required fields
    if not result.get("action_name"):
        errors.append("action_name is required")

    if "preflight_decision" not in result:
        errors.append("preflight_decision is required")

    # Policy enforcement: safe_to_execute must be false
    if result.get("safe_to_execute"):
        errors.append("safe_to_execute must be false")

    # Policy enforcement: production_allowed should be false
    if result.get("production_allowed"):
        errors.append("production_allowed must be false")

    return errors
