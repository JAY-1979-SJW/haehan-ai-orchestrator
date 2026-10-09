"""Universal Task Planner — intent + observation + site type → 실행 계획."""
from __future__ import annotations

import uuid
from typing import Any

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from core.agent_runtime.runtime.universal.unknown_site_fallback_policy import (
    get_action_grade_for_unknown_site,
)
from core.agent_runtime.runtime.universal.user_intent_parser import (
    INTENT_DELETE_POST,
    INTENT_DOWNLOAD_ATTACHMENTS,
    INTENT_EXTRACT_TABLE,
    INTENT_FIND_NOTICE,
    INTENT_GENERATE_BLOG_DRAFT,
    INTENT_PREPARE_FORM,
    INTENT_PUBLISH_POST,
    INTENT_READ_PAGE,
    INTENT_SEARCH_SITE,
    INTENT_SEND_MESSAGE,
    INTENT_SUBMIT_FORM,
    INTENT_SUMMARIZE_CONTENT,
    INTENT_UPDATE_POST,
    INTENT_WRITE_COMMENT,
    INTENT_WRITE_POST,
)

# intent → step list 매핑
_INTENT_TO_STEPS: dict[str, list[dict[str, Any]]] = {
    INTENT_READ_PAGE: [
        {"action": "open_url",       "risk": GRADE_AUTO_ALLOWED},
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
        {"action": "summarize",      "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_SEARCH_SITE: [
        {"action": "search_content", "risk": GRADE_AUTO_ALLOWED},
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_FIND_NOTICE: [
        {"action": "open_url",       "risk": GRADE_AUTO_ALLOWED},
        {"action": "find_notice",    "risk": GRADE_AUTO_ALLOWED},
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
        {"action": "summarize",      "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_DOWNLOAD_ATTACHMENTS: [
        {"action": "find_notice",    "risk": GRADE_AUTO_ALLOWED},
        {"action": "download_document", "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_SUMMARIZE_CONTENT: [
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
        {"action": "summarize",      "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_EXTRACT_TABLE: [
        {"action": "extract_table",  "risk": GRADE_AUTO_ALLOWED},
        {"action": "summarize",      "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_GENERATE_BLOG_DRAFT: [
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
        {"action": "summarize",      "risk": GRADE_AUTO_ALLOWED},
        {"action": "generate_draft", "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_PREPARE_FORM: [
        {"action": "open_url",       "risk": GRADE_AUTO_ALLOWED},
        {"action": "fill_non_sensitive_form", "risk": GRADE_AUTO_ALLOWED},
        {"action": "preview",        "risk": GRADE_AUTO_ALLOWED},
    ],
    INTENT_WRITE_POST: [
        {"action": "open_url",       "risk": GRADE_AUTO_ALLOWED},
        {"action": "generate_draft", "risk": GRADE_AUTO_ALLOWED},
        {"action": "save_draft",     "risk": GRADE_AUTO_ALLOWED},
        {"action": "write_post",     "risk": GRADE_USER_DELEGATED},
    ],
    INTENT_WRITE_COMMENT: [
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
        {"action": "generate_draft", "risk": GRADE_AUTO_ALLOWED},
        {"action": "write_comment",  "risk": GRADE_USER_DELEGATED},
    ],
    INTENT_PUBLISH_POST: [
        {"action": "save_draft",     "risk": GRADE_AUTO_ALLOWED},
        {"action": "preview",        "risk": GRADE_AUTO_ALLOWED},
        {"action": "publish_post",   "risk": GRADE_USER_DELEGATED},
    ],
    INTENT_UPDATE_POST: [
        {"action": "extract_text",   "risk": GRADE_AUTO_ALLOWED},
        {"action": "generate_draft", "risk": GRADE_AUTO_ALLOWED},
        {"action": "update_post",    "risk": GRADE_USER_DELEGATED},
    ],
    INTENT_DELETE_POST: [
        {"action": "delete_post",    "risk": GRADE_USER_DELEGATED},
    ],
    INTENT_SEND_MESSAGE: [
        {"action": "generate_draft", "risk": GRADE_AUTO_ALLOWED},
        {"action": "send_message",   "risk": GRADE_USER_DELEGATED},
    ],
    INTENT_SUBMIT_FORM: [
        {"action": "fill_non_sensitive_form", "risk": GRADE_AUTO_ALLOWED},
        {"action": "preview",        "risk": GRADE_AUTO_ALLOWED},
        {"action": "submit_non_legal_form", "risk": GRADE_USER_DELEGATED},
    ],
}


def _apply_risk_signals(steps: list[dict], risk_signals: list[str]) -> list[dict]:
    """risk signal이 있으면 DELEGATED → DIRECT 격상."""
    _risk_direct = frozenset(["payment", "sign", "bid", "transfer", "legal"])
    if not any(r in _risk_direct for r in risk_signals):
        return steps
    result = []
    for step in steps:
        s = dict(step)
        if s["risk"] == GRADE_USER_DELEGATED:
            s["risk"] = GRADE_USER_DIRECT
        result.append(s)
    return result


def create_plan(
    intent_result: dict[str, Any],
    observation: dict[str, Any],
    site_classification: dict[str, Any],
    has_permissions: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    실행 계획을 생성한다.

    반환:
      plan_id: str
      intent: str
      site_type: str
      steps: list[{step_id, action, risk, executable, reason}]
      auto_steps: list[str]
      pending_permission: list[str]
      user_direct_required: list[str]
      blocked: list[str]
      executable: bool   # 모든 REQUIRED 단계 권한 충족 여부
    """
    intent = intent_result.get("intent", "UNKNOWN")
    risk_signals = observation.get("risk_signals", [])
    site_type = site_classification.get("site_type", "unknown")
    has_permissions = has_permissions or {}

    raw_steps = _INTENT_TO_STEPS.get(intent, [
        {"action": "readonly_explore", "risk": GRADE_AUTO_ALLOWED},
        {"action": "extract_text",     "risk": GRADE_AUTO_ALLOWED},
    ])

    # risk signal에 따라 등급 조정
    raw_steps = _apply_risk_signals(raw_steps, risk_signals)

    steps = []
    auto_steps = []
    pending_permission = []
    user_direct_required = []
    blocked_actions = []

    for i, raw in enumerate(raw_steps):
        action = raw["action"]
        risk = raw.get("risk") or get_action_grade_for_unknown_site(action, risk_signals)
        step_id = f"s{i+1:02d}"

        if risk == GRADE_BLOCKED:
            blocked_actions.append(action)
            steps.append({"step_id": step_id, "action": action, "risk": risk,
                          "executable": False, "reason": "BLOCKED"})
        elif risk == GRADE_AUTO_ALLOWED:
            auto_steps.append(action)
            steps.append({"step_id": step_id, "action": action, "risk": risk,
                          "executable": True, "reason": "AUTO_ALLOWED"})
        elif risk == GRADE_USER_DIRECT:
            user_direct_required.append(action)
            steps.append({"step_id": step_id, "action": action, "risk": risk,
                          "executable": False, "reason": "USER_DIRECT_REQUIRED"})
        else:  # DELEGATED
            has_perm = has_permissions.get(action, False)
            if has_perm:
                steps.append({"step_id": step_id, "action": action, "risk": risk,
                              "executable": True, "reason": "DELEGATED — permission 확인됨"})
            else:
                pending_permission.append(action)
                steps.append({"step_id": step_id, "action": action, "risk": risk,
                              "executable": False, "reason": "USER_DELEGATED_PERMISSION_REQUIRED"})

    executable = (len(pending_permission) == 0 and len(user_direct_required) == 0
                  and len(blocked_actions) == 0)

    return {
        "plan_id": str(uuid.uuid4()),
        "intent": intent,
        "site_type": site_type,
        "steps": steps,
        "auto_steps": auto_steps,
        "pending_permission": pending_permission,
        "user_direct_required": user_direct_required,
        "blocked": blocked_actions,
        "executable": executable,
    }


def get_auto_only_plan(plan: dict[str, Any]) -> list[dict]:
    """실행 가능한 AUTO_ALLOWED step만 반환."""
    return [s for s in plan.get("steps", []) if s.get("executable") and s.get("risk") == GRADE_AUTO_ALLOWED]


def plan_has_blocked(plan: dict[str, Any]) -> bool:
    return bool(plan.get("blocked"))


def plan_needs_permission(plan: dict[str, Any]) -> bool:
    return bool(plan.get("pending_permission"))
