"""Gabia DNS 업무 공종 레지스트리.

ASSISTANT_GABIA_DNS_USER_APPROVAL_WORKFLOW_01

이 모듈은 가비아 DNS 관련 WorkTrade / ExternalWork 공종을 등록하는
단일 소스다.

핵심 원칙:
    AI는 DNS 레코드 입력 준비까지 가능하다.
    AI는 최종 저장/적용 버튼 앞에서 반드시 멈춘다.
    최초 로그인은 사용자가 직접 수행한다.
    승인된 신뢰 세션은 AI가 재사용할 수 있다.
    최종 저장은 사용자 승인 게이트를 통과해야만 실행된다.

금지:
    실제 가비아 접속 금지
    password/otp/token/cookie/session 저장 금지
    최종 저장 버튼 AI 자동 클릭 금지
    서버 직접 로그인 자동화 금지
    인증서 파일 서버 복사 금지
"""
from __future__ import annotations

from ai_orchestrator.domain.models import ExternalWork, WorkTrade

# ---------------------------------------------------------------------------
# WorkTrade 정의
# ---------------------------------------------------------------------------

GABIA_DNS_WORK_TRADE = WorkTrade(
    work_trade_id="gabia_dns_management",
    name="Gabia DNS Management",
    description=(
        "가비아 DNS 레코드 관리 업무 공종. "
        "AI가 레코드 입력 준비 → 사용자 승인 → 최종 저장 흐름으로 운영."
    ),
    scope="LOCAL_AGENT_REQUIRED",
    execution_location="LOCAL_AGENT_REQUIRED",
    external_app_hold=False,
    owner_layer="LOCAL_AGENT",
    status="active",
)

# ---------------------------------------------------------------------------
# ExternalWork 정의
# ---------------------------------------------------------------------------

GABIA_DNS_RECORD_PREPARE = ExternalWork(
    external_work_id="gabia_dns_record_prepare",
    provider="gabia",
    action_type="dns_record_prepare",
    category="LOCAL_AGENT_REQUIRED",
    execution_location="LOCAL_AGENT_REQUIRED",
    risk_level="high",
    approval_required=True,
    auth_mode="browser_session",
    status="active",
    safety_notice=(
        "AI는 DNS 레코드 입력 준비까지 가능하지만 "
        "최종 저장은 사용자 승인 필수."
    ),
    description=(
        "가비아 DNS 레코드 화면까지 진입하여 레코드 입력 초안을 준비한다. "
        "safe_to_prepare=True / safe_to_click_final_button=False."
    ),
)

GABIA_DNS_FINAL_SAVE = ExternalWork(
    external_work_id="gabia_dns_final_save",
    provider="gabia",
    action_type="dns_final_save",
    category="USER_DIRECT_REQUIRED",
    execution_location="USER_DIRECT_REQUIRED",
    risk_level="high",
    approval_required=True,
    auth_mode="user_direct",
    status="active",
    safety_notice=(
        "저장/적용 버튼은 사용자 명시적 승인 이후에만 실행 가능. "
        "AI 자동 클릭 절대 금지."
    ),
    description="가비아 DNS 최종 저장/적용 — 사용자 승인 게이트 통과 후에만 실행.",
)

GABIA_DNS_RECORD_READ = ExternalWork(
    external_work_id="gabia_dns_record_read",
    provider="gabia",
    action_type="dns_record_read",
    category="LOCAL_AGENT_REQUIRED",
    execution_location="LOCAL_AGENT_REQUIRED",
    risk_level="medium",
    approval_required=False,
    auth_mode="browser_session",
    status="active",
    safety_notice="조회 결과에 secret/token/cookie 포함 금지.",
    description="가비아 DNS 레코드 현황 조회 (read-only, 신뢰 세션 재사용 가능).",
)

# ---------------------------------------------------------------------------
# Registry 조회 API
# ---------------------------------------------------------------------------

_WORK_TRADES: dict[str, WorkTrade] = {
    GABIA_DNS_WORK_TRADE.work_trade_id: GABIA_DNS_WORK_TRADE,
}

_EXTERNAL_WORKS: dict[str, ExternalWork] = {
    GABIA_DNS_RECORD_PREPARE.external_work_id: GABIA_DNS_RECORD_PREPARE,
    GABIA_DNS_FINAL_SAVE.external_work_id: GABIA_DNS_FINAL_SAVE,
    GABIA_DNS_RECORD_READ.external_work_id: GABIA_DNS_RECORD_READ,
}


def get_work_trade(work_trade_id: str) -> WorkTrade | None:
    return _WORK_TRADES.get(work_trade_id)


def get_external_work(external_work_id: str) -> ExternalWork | None:
    return _EXTERNAL_WORKS.get(external_work_id)


def list_gabia_work_trades() -> list[WorkTrade]:
    return list(_WORK_TRADES.values())


def list_gabia_external_works() -> list[ExternalWork]:
    return list(_EXTERNAL_WORKS.values())


__all__ = [
    "GABIA_DNS_WORK_TRADE",
    "GABIA_DNS_RECORD_PREPARE",
    "GABIA_DNS_FINAL_SAVE",
    "GABIA_DNS_RECORD_READ",
    "get_work_trade",
    "get_external_work",
    "list_gabia_work_trades",
    "list_gabia_external_works",
]
