"""site_engine execution gate — 공통 실행 판단 foundation.

기존 scripts/gate.py를 대체하지 않는다.
이 모듈은 SiteProfile 기반의 공통 실행 위치·승인·차단 판단 모델을 제공한다.

판단 흐름:
  1. 작업이 profile의 allowed_capabilities 안에 있는가?
  2. 작업이 sensitive credential action인가? → BLOCKED / USER_DIRECT_REQUIRED
  3. 작업이 irreversible action(submit/publish/send/upload/delete)인가?
     → APPROVAL_REQUIRED
  4. profile의 action_policies에 명시된 gate가 있는가?
  5. default_execution_location에 따른 서버/로컬/사용자 판단

실제 실행, 브라우저 호출, DB write는 없다. 순수 판단 함수만 포함한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from scripts.site_engine.types import (
    ExecutionLocation,
    GateDecision,
    SiteCapability,
)


# ── 추가 열거형 ──────────────────────────────────────────────────────

class ExecutionDecision(str, Enum):
    ALLOWED = "ALLOWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
    USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
    BLOCKED = "BLOCKED"


class ActionSensitivity(str, Enum):
    SAFE = "SAFE"
    WRITE = "WRITE"
    IRREVERSIBLE = "IRREVERSIBLE"
    CREDENTIAL = "CREDENTIAL"
    FORBIDDEN = "FORBIDDEN"


class GateReason(str, Enum):
    ALLOWED_READ_ONLY = "ALLOWED_READ_ONLY"
    ALLOWED_SERVER_BROWSER = "ALLOWED_SERVER_BROWSER"
    APPROVAL_REQUIRED_IRREVERSIBLE = "APPROVAL_REQUIRED_IRREVERSIBLE"
    LOCAL_AGENT_REQUIRED_BY_PROFILE = "LOCAL_AGENT_REQUIRED_BY_PROFILE"
    USER_DIRECT_REQUIRED_CREDENTIAL = "USER_DIRECT_REQUIRED_CREDENTIAL"
    USER_DIRECT_REQUIRED_BY_PROFILE = "USER_DIRECT_REQUIRED_BY_PROFILE"
    BLOCKED_SENSITIVE_CREDENTIAL = "BLOCKED_SENSITIVE_CREDENTIAL"
    BLOCKED_BY_PROFILE = "BLOCKED_BY_PROFILE"
    BLOCKED_NOT_IN_ALLOWED = "BLOCKED_NOT_IN_ALLOWED"
    BLOCKED_SERVER_FORBIDDEN_SITE = "BLOCKED_SERVER_FORBIDDEN_SITE"
    BLOCKED_UNKNOWN_ACTION = "BLOCKED_UNKNOWN_ACTION"
    POLICY_OVERRIDE = "POLICY_OVERRIDE"


# ── 입출력 데이터 클래스 ──────────────────────────────────────────────

@dataclass
class ExecutionGateInput:
    site_key: str
    capability: SiteCapability
    action: str
    execution_location: ExecutionLocation = ExecutionLocation.SERVER
    is_server_forbidden_site: bool = False
    force_approved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionGateResult:
    decision: ExecutionDecision
    gate_decision: GateDecision
    reason: GateReason
    detail: str = ""
    requires_approval: bool = False
    is_blocked: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision == ExecutionDecision.ALLOWED


# ── 민감 작업 분류 ────────────────────────────────────────────────────

_IRREVERSIBLE_CAPABILITIES = frozenset({
    SiteCapability.SUBMIT,
    SiteCapability.UPLOAD,
    SiteCapability.DELETE,
    SiteCapability.PUBLISH,
    SiteCapability.SEND,
    SiteCapability.SIGN,
})

_IRREVERSIBLE_ACTION_KEYWORDS = frozenset({
    "submit", "publish", "send", "upload", "delete", "sign",
    "상신", "투찰", "발행", "전송", "삭제", "서명",
})

_CREDENTIAL_ACTION_KEYWORDS = frozenset({
    "password", "passwd", "otp", "certificate", "private_key",
    "session", "cookie", "credential", "auth_token",
    "비밀번호", "인증서", "쿠키", "세션",
})

_CREDENTIAL_EXTRACT_KEYWORDS = frozenset({
    "extract", "get", "read", "dump", "export", "fetch",
    "추출", "가져오기", "읽기", "내보내기",
})


def classify_action_sensitivity(action: str, capability: SiteCapability) -> ActionSensitivity:
    lower = action.lower()

    if capability in _IRREVERSIBLE_CAPABILITIES:
        return ActionSensitivity.IRREVERSIBLE

    if any(k in lower for k in _CREDENTIAL_ACTION_KEYWORDS):
        if any(k in lower for k in _CREDENTIAL_EXTRACT_KEYWORDS):
            return ActionSensitivity.FORBIDDEN
        return ActionSensitivity.CREDENTIAL

    if any(k in lower for k in _IRREVERSIBLE_ACTION_KEYWORDS):
        return ActionSensitivity.IRREVERSIBLE

    if capability == SiteCapability.READ or capability == SiteCapability.SEARCH:
        return ActionSensitivity.SAFE

    return ActionSensitivity.WRITE


# ── 핵심 판단 함수 ────────────────────────────────────────────────────

def evaluate_execution_gate(
    gate_input: ExecutionGateInput,
    profile=None,  # Optional[SiteProfile] — circular import 방지로 Any 허용
) -> ExecutionGateResult:
    """실행 gate 판단.

    profile이 있으면 SiteProfile 정책을 우선 적용한다.
    profile이 없으면 action/capability 기반 기본 정책을 적용한다.
    """
    cap = gate_input.capability
    action = gate_input.action

    # 1. profile 기반 명시 gate 확인
    if profile is not None:
        if not profile.is_capability_allowed(cap):
            return ExecutionGateResult(
                decision=ExecutionDecision.BLOCKED,
                gate_decision=GateDecision.BLOCKED,
                reason=GateReason.BLOCKED_NOT_IN_ALLOWED,
                detail=f"capability {cap} is not in allowed_capabilities for site {profile.key}",
                is_blocked=True,
            )
        profile_gate = profile.get_gate(cap)
        if profile_gate == GateDecision.BLOCKED:
            return ExecutionGateResult(
                decision=ExecutionDecision.BLOCKED,
                gate_decision=GateDecision.BLOCKED,
                reason=GateReason.BLOCKED_BY_PROFILE,
                detail=f"SiteProfile {profile.key!r} blocks capability {cap}",
                is_blocked=True,
            )
        if profile_gate == GateDecision.LOCAL_AGENT_REQUIRED:
            return ExecutionGateResult(
                decision=ExecutionDecision.LOCAL_AGENT_REQUIRED,
                gate_decision=GateDecision.LOCAL_AGENT_REQUIRED,
                reason=GateReason.LOCAL_AGENT_REQUIRED_BY_PROFILE,
                detail="SiteProfile requires local-agent execution",
            )
        if profile_gate == GateDecision.USER_DIRECT_REQUIRED:
            return ExecutionGateResult(
                decision=ExecutionDecision.USER_DIRECT_REQUIRED,
                gate_decision=GateDecision.USER_DIRECT_REQUIRED,
                reason=GateReason.USER_DIRECT_REQUIRED_BY_PROFILE,
                detail="SiteProfile requires user direct operation",
            )

    # 2. 서버 금지 사이트에서 서버 브라우저 시도
    if gate_input.is_server_forbidden_site and gate_input.execution_location == ExecutionLocation.SERVER:
        return ExecutionGateResult(
            decision=ExecutionDecision.BLOCKED,
            gate_decision=GateDecision.BLOCKED,
            reason=GateReason.BLOCKED_SERVER_FORBIDDEN_SITE,
            detail="Server-side browser automation is forbidden for this site type",
            is_blocked=True,
        )

    # 3. 민감 자격증명 액션 분류
    sensitivity = classify_action_sensitivity(action, cap)

    if sensitivity == ActionSensitivity.FORBIDDEN:
        return ExecutionGateResult(
            decision=ExecutionDecision.BLOCKED,
            gate_decision=GateDecision.BLOCKED,
            reason=GateReason.BLOCKED_SENSITIVE_CREDENTIAL,
            detail=f"Credential extraction action is forbidden: {action!r}",
            is_blocked=True,
        )

    if sensitivity == ActionSensitivity.CREDENTIAL:
        return ExecutionGateResult(
            decision=ExecutionDecision.USER_DIRECT_REQUIRED,
            gate_decision=GateDecision.USER_DIRECT_REQUIRED,
            reason=GateReason.USER_DIRECT_REQUIRED_CREDENTIAL,
            detail=f"Credential-related action requires user direct input: {action!r}",
        )

    # 4. 비가역 작업 — force_approved가 있어야 통과
    if sensitivity == ActionSensitivity.IRREVERSIBLE:
        if gate_input.force_approved:
            return ExecutionGateResult(
                decision=ExecutionDecision.ALLOWED,
                gate_decision=GateDecision.APPROVAL_REQUIRED,
                reason=GateReason.POLICY_OVERRIDE,
                detail="force_approved: irreversible action allowed by prior approval",
                requires_approval=True,
            )
        return ExecutionGateResult(
            decision=ExecutionDecision.APPROVAL_REQUIRED,
            gate_decision=GateDecision.APPROVAL_REQUIRED,
            reason=GateReason.APPROVAL_REQUIRED_IRREVERSIBLE,
            detail=f"Irreversible action requires prior approval: {action!r}",
            requires_approval=True,
        )

    # 5. 읽기 전용 — 허용
    if sensitivity == ActionSensitivity.SAFE:
        return ExecutionGateResult(
            decision=ExecutionDecision.ALLOWED,
            gate_decision=GateDecision.READ_ONLY_ALLOWED,
            reason=GateReason.ALLOWED_READ_ONLY,
            detail="Read-only action allowed",
        )

    # 6. WRITE — 서버 브라우저 허용 범주
    return ExecutionGateResult(
        decision=ExecutionDecision.ALLOWED,
        gate_decision=GateDecision.SERVER_BROWSER_ALLOWED,
        reason=GateReason.ALLOWED_SERVER_BROWSER,
        detail="Write action allowed on server browser",
    )


def require_approval_for_action(action: str, capability: SiteCapability) -> bool:
    """이 action/capability 조합이 사전 승인을 필요로 하는지 반환."""
    return classify_action_sensitivity(action, capability) == ActionSensitivity.IRREVERSIBLE


def block_for_sensitive_credential_action(action: str) -> bool:
    """credential 추출 시도인지 판단. True면 차단 대상."""
    lower = action.lower()
    has_cred = any(k in lower for k in _CREDENTIAL_ACTION_KEYWORDS)
    has_extract = any(k in lower for k in _CREDENTIAL_EXTRACT_KEYWORDS)
    return has_cred and has_extract


def resolve_execution_location(
    profile=None,
    capability: Optional[SiteCapability] = None,
) -> ExecutionLocation:
    """SiteProfile과 capability 기반으로 적절한 실행 위치를 반환."""
    if profile is None:
        return ExecutionLocation.SERVER
    if capability is not None:
        gate = profile.get_gate(capability)
        if gate == GateDecision.LOCAL_AGENT_REQUIRED:
            return ExecutionLocation.LOCAL_AGENT
        if gate == GateDecision.USER_DIRECT_REQUIRED:
            return ExecutionLocation.USER_DIRECT
    return profile.default_execution_location
