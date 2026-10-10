"""Gabia 브라우저 업무 자동화 계약 및 상태 머신.

ASSISTANT_GABIA_BROWSER_USER_PRESENT_AUTOMATION_PLAN_01

이 모듈은 가비아 DNS 업무를 위한 브라우저 자동화 계약과 상태 머신을 정의한다.
실제 브라우저 접속 없이 mock/contract 중심으로 설계한다.

핵심 원칙:
    AI는 DNS 관리 화면까지 자동 진입 가능 (safe_to_prepare=True).
    최초 로그인은 반드시 사용자 직접 수행 (USER_PRESENT_AUTH).
    승인된 신뢰 세션은 재사용 가능 (TRUSTED_SESSION_REUSE).
    최종 저장/적용 버튼은 AI가 자동 클릭 불가 (safe_to_click_final_button=False).
    모든 상태 전이는 이 모듈의 상태 머신을 따른다.

금지:
    password/OTP/cert_password/token/cookie/session 저장 금지
    실제 가비아 접속 금지 (이 모듈은 contract만 정의)
    최종 저장 버튼 자동 클릭 금지
    서버 직접 로그인 자동화 금지
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 상태 머신 상태 상수
# ---------------------------------------------------------------------------

STATE_OPEN_GABIA_HOME = "OPEN_GABIA_HOME"
STATE_LOGIN_REQUIRED = "LOGIN_REQUIRED"
STATE_USER_PRESENT_AUTH_IN_PROGRESS = "USER_PRESENT_AUTH_IN_PROGRESS"
STATE_TRUSTED_SESSION_REUSED = "TRUSTED_SESSION_REUSED"
STATE_DNS_MANAGEMENT_PAGE_READY = "DNS_MANAGEMENT_PAGE_READY"
STATE_DNS_RECORD_DRAFTED = "DNS_RECORD_DRAFTED"
STATE_CHANGE_PREVIEW_CREATED = "CHANGE_PREVIEW_CREATED"
STATE_FINAL_APPROVAL_REQUIRED = "FINAL_APPROVAL_REQUIRED"
STATE_USER_APPROVED_FINAL_SAVE = "USER_APPROVED_FINAL_SAVE"
STATE_REAUTH_REQUIRED = "REAUTH_REQUIRED"
STATE_BLOCKED = "BLOCKED"

# 상태 전이 정의 — 허용된 전이만 명시
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_OPEN_GABIA_HOME: frozenset({STATE_LOGIN_REQUIRED, STATE_TRUSTED_SESSION_REUSED}),
    STATE_LOGIN_REQUIRED: frozenset({STATE_USER_PRESENT_AUTH_IN_PROGRESS, STATE_BLOCKED}),
    STATE_USER_PRESENT_AUTH_IN_PROGRESS: frozenset(
        {STATE_DNS_MANAGEMENT_PAGE_READY, STATE_BLOCKED, STATE_LOGIN_REQUIRED}
    ),
    STATE_TRUSTED_SESSION_REUSED: frozenset({STATE_DNS_MANAGEMENT_PAGE_READY, STATE_REAUTH_REQUIRED}),
    STATE_DNS_MANAGEMENT_PAGE_READY: frozenset({STATE_DNS_RECORD_DRAFTED, STATE_REAUTH_REQUIRED}),
    STATE_DNS_RECORD_DRAFTED: frozenset({STATE_CHANGE_PREVIEW_CREATED}),
    STATE_CHANGE_PREVIEW_CREATED: frozenset({STATE_FINAL_APPROVAL_REQUIRED}),
    STATE_FINAL_APPROVAL_REQUIRED: frozenset({STATE_USER_APPROVED_FINAL_SAVE}),
    STATE_USER_APPROVED_FINAL_SAVE: frozenset(),  # 다음 공정에서 실제 저장
    STATE_REAUTH_REQUIRED: frozenset({STATE_USER_PRESENT_AUTH_IN_PROGRESS}),
    STATE_BLOCKED: frozenset(),
}

# AI 자동 실행 가능한 상태 (safe_to_prepare=True 해당 상태)
AI_EXECUTABLE_STATES: frozenset[str] = frozenset(
    {
        STATE_OPEN_GABIA_HOME,
        STATE_TRUSTED_SESSION_REUSED,
        STATE_DNS_MANAGEMENT_PAGE_READY,
        STATE_DNS_RECORD_DRAFTED,
        STATE_CHANGE_PREVIEW_CREATED,
    }
)

# 사용자 직접 개입 필요 상태
USER_REQUIRED_STATES: frozenset[str] = frozenset(
    {
        STATE_LOGIN_REQUIRED,
        STATE_USER_PRESENT_AUTH_IN_PROGRESS,
        STATE_FINAL_APPROVAL_REQUIRED,
        STATE_REAUTH_REQUIRED,
        STATE_USER_APPROVED_FINAL_SAVE,
    }
)

# AI가 절대 자동 실행 불가한 상태 (final button)
FINAL_BUTTON_BLOCKED_STATES: frozenset[str] = frozenset(
    {
        STATE_FINAL_APPROVAL_REQUIRED,
        STATE_USER_APPROVED_FINAL_SAVE,
        STATE_BLOCKED,
    }
)


def is_transition_allowed(from_state: str, to_state: str) -> bool:
    """상태 전이가 허용되는지 확인한다."""
    return to_state in ALLOWED_TRANSITIONS.get(from_state, frozenset())


def is_ai_executable(state: str) -> bool:
    """해당 상태에서 AI가 자동 실행 가능한지 확인한다."""
    return state in AI_EXECUTABLE_STATES


def is_final_button_blocked(state: str) -> bool:
    """해당 상태에서 최종 버튼 자동 클릭이 차단되는지 확인한다."""
    return state in FINAL_BUTTON_BLOCKED_STATES


# ---------------------------------------------------------------------------
# GabiaBrowserTask — 브라우저 작업 계약
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GabiaBrowserTask:
    """가비아 DNS 브라우저 작업 계약 모델.

    safe_to_prepare=True: AI가 레코드 입력 준비까지 가능.
    safe_to_click_final_button=False: AI가 최종 버튼 클릭 불가.
    requires_final_approval=True: 저장 전 사용자 승인 필수.

    금지 필드: password, otp, cert_password, token, cookie, session
    """

    task_id: str
    provider: str  # gabia
    purpose: str  # dns_record_prepare
    target_domain: str  # haehan-ai.kr
    subdomain: str  # autowork
    desired_fqdn: str  # autowork.haehan-ai.kr
    record_type: str  # A 또는 CNAME
    value_source: str  # SERVER_PUBLIC_IP or TARGET_HOST
    execution_location: str = "LOCAL_AGENT_REQUIRED"
    auth_mode: str = "USER_PRESENT_AUTH"  # USER_PRESENT_AUTH or TRUSTED_SESSION_REUSE
    safe_to_prepare: bool = True
    safe_to_click_final_button: bool = False
    requires_final_approval: bool = True
    final_button_blocked: bool = True
    current_state: str = STATE_OPEN_GABIA_HOME

    def is_ai_executable_now(self) -> bool:
        return is_ai_executable(self.current_state)

    def is_blocked_now(self) -> bool:
        return self.current_state == STATE_BLOCKED

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "provider": self.provider,
            "purpose": self.purpose,
            "target_domain": self.target_domain,
            "subdomain": self.subdomain,
            "desired_fqdn": self.desired_fqdn,
            "record_type": self.record_type,
            "value_source": self.value_source,
            "execution_location": self.execution_location,
            "auth_mode": self.auth_mode,
            "safe_to_prepare": self.safe_to_prepare,
            "safe_to_click_final_button": self.safe_to_click_final_button,
            "requires_final_approval": self.requires_final_approval,
            "final_button_blocked": self.final_button_blocked,
            "current_state": self.current_state,
        }


# ---------------------------------------------------------------------------
# 상태 전이 결과 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateTransitionResult:
    """상태 전이 결과."""

    from_state: str
    to_state: str
    allowed: bool
    reason: str
    ai_executable: bool
    user_required: bool
    final_button_blocked: bool

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "allowed": self.allowed,
            "reason": self.reason,
            "ai_executable": self.ai_executable,
            "user_required": self.user_required,
            "final_button_blocked": self.final_button_blocked,
        }


def evaluate_transition(from_state: str, to_state: str) -> StateTransitionResult:
    """상태 전이를 평가하고 결과를 반환한다."""
    allowed = is_transition_allowed(from_state, to_state)
    ai_exec = is_ai_executable(to_state)
    user_req = to_state in USER_REQUIRED_STATES
    final_blocked = is_final_button_blocked(to_state)

    if not allowed:
        reason = f"{from_state} → {to_state} 전이 불가"
    elif to_state == STATE_FINAL_APPROVAL_REQUIRED:
        reason = "최종 저장 버튼 앞에서 정지 — 사용자 승인 대기"
    elif to_state in USER_REQUIRED_STATES:
        reason = f"사용자 직접 개입 필요: {to_state}"
    elif ai_exec:
        reason = f"AI 자동 실행 가능: {to_state}"
    else:
        reason = f"상태 전이: {from_state} → {to_state}"

    return StateTransitionResult(
        from_state=from_state,
        to_state=to_state,
        allowed=allowed,
        reason=reason,
        ai_executable=ai_exec,
        user_required=user_req,
        final_button_blocked=final_blocked,
    )


# ---------------------------------------------------------------------------
# 표준 autowork 작업 생성 헬퍼
# ---------------------------------------------------------------------------


def make_autowork_dns_task(
    value_source: str = "SERVER_PUBLIC_IP_PENDING",
    auth_mode: str = "USER_PRESENT_AUTH",
) -> GabiaBrowserTask:
    """autowork.haehan-ai.kr DNS 레코드 준비 작업을 반환한다.

    value_source: 서버 IP는 대표님 확인 후 채운다.
    auth_mode: 첫 진입은 USER_PRESENT_AUTH, 재진입은 TRUSTED_SESSION_REUSE.
    """
    return GabiaBrowserTask(
        task_id="gabia_autowork_dns_prepare_001",
        provider="gabia",
        purpose="dns_record_prepare",
        target_domain="haehan-ai.kr",
        subdomain="autowork",
        desired_fqdn="autowork.haehan-ai.kr",
        record_type="A",
        value_source=value_source,
        execution_location="LOCAL_AGENT_REQUIRED",
        auth_mode=auth_mode,
        safe_to_prepare=True,
        safe_to_click_final_button=False,
        requires_final_approval=True,
        final_button_blocked=True,
        current_state=STATE_OPEN_GABIA_HOME,
    )


# ---------------------------------------------------------------------------
# Gabia 네비게이션 계획 상수
# ---------------------------------------------------------------------------

GABIA_HOME_URL = "https://www.gabia.com"
GABIA_LOGIN_URL = "https://www.gabia.com/login"
GABIA_DNS_MGMT_PATH = "/mypage/service/domain/dns"  # 로그인 후 진입 경로

GABIA_NAV_PLAN: tuple[dict[str, Any], ...] = (
    {"step": 1, "state": STATE_OPEN_GABIA_HOME, "actor": "AI", "action": "가비아 홈 접속", "safe_to_auto": True},
    {"step": 2, "state": STATE_LOGIN_REQUIRED, "actor": "AI", "action": "로그인 상태 감지", "safe_to_auto": True},
    {
        "step": 3,
        "state": STATE_USER_PRESENT_AUTH_IN_PROGRESS,
        "actor": "USER",
        "action": "대표님 직접 로그인",
        "safe_to_auto": False,
    },
    {
        "step": 4,
        "state": STATE_DNS_MANAGEMENT_PAGE_READY,
        "actor": "AI",
        "action": "DNS 관리 화면 이동",
        "safe_to_auto": True,
    },
    {
        "step": 5,
        "state": STATE_DNS_RECORD_DRAFTED,
        "actor": "AI",
        "action": "레코드 값 입력 준비",
        "safe_to_auto": True,
    },
    {
        "step": 6,
        "state": STATE_CHANGE_PREVIEW_CREATED,
        "actor": "AI",
        "action": "변경 전/후 비교표 생성",
        "safe_to_auto": True,
    },
    {
        "step": 7,
        "state": STATE_FINAL_APPROVAL_REQUIRED,
        "actor": "USER",
        "action": "최종 저장 버튼 앞에서 정지 — 승인 대기",
        "safe_to_auto": False,
    },
    {
        "step": 8,
        "state": STATE_USER_APPROVED_FINAL_SAVE,
        "actor": "USER",
        "action": "대표님 승인 후 저장 (다음 공정)",
        "safe_to_auto": False,
    },
)


__all__ = [  # noqa: RUF022
    "GabiaBrowserTask",
    "StateTransitionResult",
    "make_autowork_dns_task",
    "evaluate_transition",
    "is_transition_allowed",
    "is_ai_executable",
    "is_final_button_blocked",
    # 상태 상수
    "STATE_OPEN_GABIA_HOME",
    "STATE_LOGIN_REQUIRED",
    "STATE_USER_PRESENT_AUTH_IN_PROGRESS",
    "STATE_TRUSTED_SESSION_REUSED",
    "STATE_DNS_MANAGEMENT_PAGE_READY",
    "STATE_DNS_RECORD_DRAFTED",
    "STATE_CHANGE_PREVIEW_CREATED",
    "STATE_FINAL_APPROVAL_REQUIRED",
    "STATE_USER_APPROVED_FINAL_SAVE",
    "STATE_REAUTH_REQUIRED",
    "STATE_BLOCKED",
    "ALLOWED_TRANSITIONS",
    "AI_EXECUTABLE_STATES",
    "USER_REQUIRED_STATES",
    "FINAL_BUTTON_BLOCKED_STATES",
    "GABIA_HOME_URL",
    "GABIA_DNS_MGMT_PATH",
    "GABIA_NAV_PLAN",
]
