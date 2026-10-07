"""Gabia SiteProfile definition.

가비아는 도메인/DNS/호스팅/메일/결제/계정 변경이 가능한 고위험 사이트.
write/change/payment 계열은 반드시 승인형 또는 사용자 직접 조작으로 분리.
"""
from __future__ import annotations

from scripts.site_engine.profiles import SiteActionPolicy, SiteProfile
from scripts.site_engine.site_types import GateDecision, SiteCapability, SiteProfileStatus

GABIA_PROFILE = SiteProfile(
    key="gabia",
    base_url="https://www.gabia.com",
    display_name="Gabia",
    login_domain_hints=["gabia.com", "my.gabia.com", "accounts.gabia.com", "dns.gabia.com"],
    allowed_capabilities={
        SiteCapability.READ,
        SiteCapability.SEARCH,
        SiteCapability.SUBMIT,
        SiteCapability.DELETE,
    },
    blocked_capabilities={
        # 비밀번호/세션/쿠키 추출 — 절대 금지
        SiteCapability.SIGN,
    },
    action_policies={
        # 공개 페이지 read: 허용
        SiteCapability.READ: SiteActionPolicy(
            capability=SiteCapability.READ,
            gate=GateDecision.READ_ONLY_ALLOWED,
            requires_approval=False,
            is_irreversible=False,
        ),
        # DNS 레코드 생성/변경, 도메인 연장/이전 등 — 승인 필수
        SiteCapability.SUBMIT: SiteActionPolicy(
            capability=SiteCapability.SUBMIT,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
        # DNS 레코드 삭제, 도메인 취소 등 — 승인 필수 (비가역)
        SiteCapability.DELETE: SiteActionPolicy(
            capability=SiteCapability.DELETE,
            gate=GateDecision.APPROVAL_REQUIRED,
            requires_approval=True,
            is_irreversible=True,
        ),
        # 로그인/OTP/2FA/결제 — 사용자 직접 수행 필수 (SIGN capability로 표현)
        SiteCapability.SIGN: SiteActionPolicy(
            capability=SiteCapability.SIGN,
            gate=GateDecision.BLOCKED,
            requires_approval=False,
            is_irreversible=False,
        ),
    },
    status=SiteProfileStatus.ACTIVE,
)
