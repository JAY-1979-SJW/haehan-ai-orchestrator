"""Gabia risk gate helpers using site_engine execution_gate.

가비아 gate 정책:
  - public read/status/check  : READ_ONLY_ALLOWED
  - account info (logged-in)  : LOCAL_AGENT_REQUIRED (SIGN → BLOCKED 경계 활용)
  - login/password/OTP/2FA    : USER_DIRECT_REQUIRED (evaluate 결과로 표현)
  - DNS create/update/delete  : APPROVAL_REQUIRED
  - domain renew/transfer     : APPROVAL_REQUIRED
  - hosting/mail setting      : APPROVAL_REQUIRED
  - payment/billing/refund    : USER_DIRECT_REQUIRED
  - password/session/cookie   : BLOCKED (SIGN capability)
"""
from __future__ import annotations

from scripts.site_engine.execution_gate import (
    ExecutionGateInput,
    ExecutionGateResult,
    evaluate_execution_gate,
)
from scripts.site_engine.site_types import SiteCapability

# profile을 lazy import로 순환 방지 후 전달 — BLOCKED/USER_DIRECT 정책을 정확히 적용
def _profile():
    from scripts.gabia.site_profile import GABIA_PROFILE
    return GABIA_PROFILE


def gate_gabia_public_read() -> ExecutionGateResult:
    """공개 페이지 읽기 (도메인 상태 등 로그인 불필요 페이지)."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.READ,
            action="public_read",
        )
    )


def gate_gabia_account_read() -> ExecutionGateResult:
    """로그인 후 계정 정보 조회 — 서버 사이드 브라우저 금지, 로컬 에이전트 필요."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.READ,
            action="account_read",
            is_server_forbidden_site=True,
        )
    )


def gate_gabia_login() -> ExecutionGateResult:
    """로그인/OTP/2FA — SIGN capability → profile BLOCKED."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.SIGN,
            action="login",
        ),
        profile=_profile(),
    )


def gate_gabia_dns_change() -> ExecutionGateResult:
    """DNS 레코드 생성/변경 — 승인 필수."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.SUBMIT,
            action="dns_record_change",
        )
    )


def gate_gabia_dns_delete() -> ExecutionGateResult:
    """DNS 레코드 삭제 — 승인 필수 (비가역)."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.DELETE,
            action="dns_record_delete",
        )
    )


def gate_gabia_domain_renew() -> ExecutionGateResult:
    """도메인 연장/이전/취소 — 승인 필수 (비가역)."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.SUBMIT,
            action="domain_renew",
        )
    )


def gate_gabia_hosting_change() -> ExecutionGateResult:
    """호스팅/메일 설정 변경 — 승인 필수."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.SUBMIT,
            action="hosting_setting_change",
        )
    )


def gate_gabia_payment() -> ExecutionGateResult:
    """결제/청구/환불 — SIGN capability → profile BLOCKED."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.SIGN,
            action="payment",
        ),
        profile=_profile(),
    )


def gate_gabia_credential_extract() -> ExecutionGateResult:
    """비밀번호/세션/쿠키/토큰 추출 — profile BLOCKED."""
    return evaluate_execution_gate(
        ExecutionGateInput(
            site_key="gabia",
            capability=SiteCapability.SIGN,
            action="credential_extract",
        ),
        profile=_profile(),
    )
