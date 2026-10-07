"""G2B 세대 실행 게이트.

실제 G2B 접속, 로그인, 투찰, 전자서명 구현 없음.
순수 판단 함수만 포함.
"""

from __future__ import annotations

from typing import Any

from scripts.g2b.site_profile import (
    BLOCKED_ACTIONS,
    DOWNLOAD_ACTIONS,
    DRAFT_ACTIONS,
    LOCAL_AGENT_REQUIRED_ACTIONS,
    READ_ONLY_ACTIONS,
    USER_DIRECT_REQUIRED_ACTIONS,
)

# ── 결정 상수 ─────────────────────────────────────────────────────────

DECISION_ALLOWED = "ALLOWED"
DECISION_READ_ONLY_ALLOWED = "READ_ONLY_ALLOWED"
DECISION_DRAFT_ALLOWED = "DRAFT_ALLOWED"
DECISION_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
DECISION_USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
DECISION_LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
DECISION_BLOCKED = "BLOCKED"

# ── 판단 함수 ─────────────────────────────────────────────────────────


def is_g2b_readonly_action(action: str) -> bool:
    return action in READ_ONLY_ACTIONS


def is_g2b_download_action(action: str) -> bool:
    return action in DOWNLOAD_ACTIONS


def is_g2b_draft_action(action: str) -> bool:
    return action in DRAFT_ACTIONS


def is_g2b_local_agent_required_action(action: str) -> bool:
    return action in LOCAL_AGENT_REQUIRED_ACTIONS


def is_g2b_user_direct_required_action(action: str) -> bool:
    return action in USER_DIRECT_REQUIRED_ACTIONS


def is_g2b_blocked_action(action: str) -> bool:
    return action in BLOCKED_ACTIONS


def is_g2b_secret_session_action(action: str) -> bool:
    _secret_keywords = ("password", "session", "cookie", "token", "extract_")
    return any(k in action for k in _secret_keywords)


# ── 통합 게이트 ───────────────────────────────────────────────────────


def evaluate_g2b_action_gate(
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if is_g2b_blocked_action(action) or is_g2b_secret_session_action(action):
        return build_g2b_gate_result(
            action,
            DECISION_BLOCKED,
            "G2B 보안 정책: 이 action은 자동 실행이 금지됩니다.",
        )
    if is_g2b_user_direct_required_action(action):
        return build_g2b_gate_result(
            action,
            DECISION_USER_DIRECT_REQUIRED,
            "사용자가 직접 수행해야 합니다 (공동인증서/OTP).",
        )
    if is_g2b_local_agent_required_action(action):
        return build_g2b_gate_result(
            action,
            DECISION_LOCAL_AGENT_REQUIRED,
            "Local Agent PC에서만 실행 가능합니다.",
        )
    if is_g2b_draft_action(action):
        return build_g2b_gate_result(
            action,
            DECISION_DRAFT_ALLOWED,
            "초안 생성 허용. 최종 제출은 사용자 직접 수행 필요.",
        )
    if is_g2b_download_action(action):
        return build_g2b_gate_result(
            action,
            DECISION_LOCAL_AGENT_REQUIRED,
            "첨부파일 다운로드는 Local Agent PC에서만 실행 가능합니다.",
        )
    if is_g2b_readonly_action(action):
        return build_g2b_gate_result(
            action,
            DECISION_READ_ONLY_ALLOWED,
            "읽기 전용 작업 허용.",
        )
    return build_g2b_gate_result(
        action,
        DECISION_BLOCKED,
        f"알 수 없는 action: '{action}'. 허용 목록에 없습니다.",
    )


def build_g2b_gate_result(
    action: str,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "decision": decision,
        "reason": reason,
        "user_direct_required": decision == DECISION_USER_DIRECT_REQUIRED,
        "local_agent_required": decision == DECISION_LOCAL_AGENT_REQUIRED,
        "approval_required": decision == DECISION_APPROVAL_REQUIRED,
        "blocked": decision == DECISION_BLOCKED,
        "draft_allowed": decision == DECISION_DRAFT_ALLOWED,
        "read_only_allowed": decision == DECISION_READ_ONLY_ALLOWED,
    }
