"""
사용자 위임 권한 게이트

task 실행 전 action 등급 + 권한 유효성 통합 검증.
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DIRECT,
    classify_action,
)
from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_ALLOWED,
    CHECK_BLOCKED,
    CHECK_PERMISSION_REQUIRED,
)
from core.agent_runtime.runtime.permission.delegated_permission_store import use_permission

# ── 게이트 결과 상수 ───────────────────────────────────────────────────────────

GATE_PASS = "GATE_PASS"  # noqa: S105
GATE_NEED_PERMISSION = "GATE_NEED_PERMISSION"
GATE_USER_DIRECT = "GATE_USER_DIRECT_REQUIRED"
GATE_BLOCKED = "GATE_BLOCKED"


def evaluate_gate(
    action: str,
    domain: str,
    permission_id: str | None = None,
    account: str = "",
    task_scope: str = "",
) -> dict[str, Any]:
    """
    action과 권한을 종합 평가한다.

    반환:
      gate: GATE_PASS | GATE_NEED_PERMISSION | GATE_USER_DIRECT | GATE_BLOCKED
      grade: 4개 등급 중 하나
      check_result: (권한 검증 결과, AUTO_ALLOWED면 None)
      reason: str
      permission_id: str | None
    """
    grade = classify_action(action)

    if grade == GRADE_BLOCKED:
        return {
            "gate": GATE_BLOCKED,
            "grade": grade,
            "check_result": CHECK_BLOCKED,
            "reason": f"BLOCKED 등급 action: {action!r}. 권한 부여 불가.",
            "permission_id": permission_id,
        }

    if grade == GRADE_USER_DIRECT:
        return {
            "gate": GATE_USER_DIRECT,
            "grade": grade,
            "check_result": None,
            "reason": f"사용자 직접 수행 필요: {action!r}",
            "permission_id": permission_id,
        }

    if grade == GRADE_AUTO_ALLOWED:
        return {
            "gate": GATE_PASS,
            "grade": grade,
            "check_result": CHECK_ALLOWED,
            "reason": f"AUTO_ALLOWED: {action!r}",
            "permission_id": permission_id,
        }

    # USER_DELEGATED
    if not permission_id:
        return {
            "gate": GATE_NEED_PERMISSION,
            "grade": grade,
            "check_result": CHECK_PERMISSION_REQUIRED,
            "reason": f"권한 없음. action={action!r}에 대한 사용자 위임 권한이 필요합니다.",
            "permission_id": None,
        }

    check = use_permission(permission_id, action, domain, account, task_scope)
    if check["result"] == CHECK_ALLOWED:
        return {
            "gate": GATE_PASS,
            "grade": grade,
            "check_result": CHECK_ALLOWED,
            "reason": f"위임 권한 유효: {action!r}",
            "permission_id": permission_id,
        }

    # EXPIRED / REVOKED / EXHAUSTED / SCOPE_EXCEEDED
    return {
        "gate": GATE_NEED_PERMISSION,
        "grade": grade,
        "check_result": check["result"],
        "reason": check["reason"],
        "permission_id": permission_id,
    }
