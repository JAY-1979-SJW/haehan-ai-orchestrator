"""USER_PRESENT 런타임용 사이트 정책 게이트 (stub 수준).

기존 ai_orchestrator/browser_tool/policy/site_compliance_policy.py 의 평가 결과를
3종 정책(API_ONLY / USER_PRESENT_LOCAL_ONLY / AUTOMATION_BLOCKED) 기준으로
allowlist/blocklist 형태로 압축한다.

본 공정 범위:
  - 정책 DB, 복잡한 규칙 엔진, 외부 사이트 자동화 확장 금지.
  - 단일 평가 함수만 제공. enforcement 는 서버 라우터 1차, 로컬 adapter 2차,
    sender 검증 3차 구조를 유지.
"""

from __future__ import annotations

from typing import Any

try:
    from ai_orchestrator.browser_tool.policy.site_compliance_policy import (
        evaluate_site_compliance as _evaluate,
    )
except Exception:  # pragma: no cover - import 경로 안전망  # noqa: BLE001 - site_compliance_policy 모듈 import 실패 시 _evaluate=None 처리 - evaluate_gate()가 _evaluate is None 인 경우 allowed=False, policy=AUTOMATION_BLOCKED 로 fail-closed 반환하도록 아래에서 명시적으로 확인함(차단 방향), 허용으로 폴백하지 않음
    _evaluate = None  # type: ignore[assignment]


POLICY_API_ONLY = "API_ONLY"
POLICY_USER_PRESENT_LOCAL_ONLY = "USER_PRESENT_LOCAL_ONLY"
POLICY_AUTOMATION_BLOCKED = "AUTOMATION_BLOCKED"

_BLOCKING_DECISIONS = frozenset(
    {
        "BLOCK",
        "REQUIRE_API_CONNECTOR",
    }
)

_USER_PRESENT_REQUIRED_DECISIONS = frozenset(
    {
        "REQUIRE_USER_PRESENT_LOCAL",
    }
)


def evaluate_gate(payload: dict[str, Any]) -> dict[str, Any]:
    """단일 진입점.

    Returns:
        {
            "allowed": bool,            # True 면 (현재 user_present 상태에서) 진행 가능
            "policy": str,              # 압축된 3종 정책 라벨
            "reason": str,              # 차단/허용 사유 코드
            "user_present_required": bool,
            "message_ko": str,
        }
    """
    if _evaluate is None:
        return {
            "allowed": False,
            "policy": POLICY_AUTOMATION_BLOCKED,
            "reason": "SITE_COMPLIANCE_MODULE_UNAVAILABLE",
            "user_present_required": False,
            "message_ko": "사이트 정책 모듈을 불러올 수 없습니다.",
        }

    raw = _evaluate(payload)
    decision = str(raw.get("compliance_decision", "BLOCK"))
    capability = str(raw.get("site_capability", "AUTOMATION_BLOCKED"))
    block_reason = raw.get("block_reason") or ""

    if capability in ("OAUTH_API_ONLY", "API_ONLY", "WORKSPACE_ADMIN_DELEGATED_API"):
        policy = POLICY_API_ONLY
    elif capability == "USER_PRESENT_LOCAL_ONLY":
        policy = POLICY_USER_PRESENT_LOCAL_ONLY
    elif capability == "AUTOMATION_BLOCKED":
        policy = POLICY_AUTOMATION_BLOCKED
    else:
        policy = capability

    user_present_required = decision in _USER_PRESENT_REQUIRED_DECISIONS
    allowed = (decision not in _BLOCKING_DECISIONS) and bool(raw.get("safe_to_dispatch", False))

    return {
        "allowed": allowed,
        "policy": policy,
        "reason": str(block_reason) if not allowed else "",
        "user_present_required": user_present_required,
        "message_ko": str(raw.get("message_ko", "")),
    }


def is_blocked(payload: dict[str, Any]) -> bool:
    """간편 blocklist 판정."""
    return not evaluate_gate(payload).get("allowed", False)
