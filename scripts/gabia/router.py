"""Gabia site router.

지원 command:
  status        - 도메인/서비스 상태 조회 계획 표시 (read-only)
  dns           - DNS 레코드 조회 계획 표시 (read-only)
  login         - 로그인 gate 정책 안내 (사용자 직접 수행)
  domain        - 도메인 관리 gate 정책 안내 (승인 필수)
  hosting       - 호스팅/메일 설정 gate 정책 안내 (승인 필수)
  payment       - 결제 gate 정책 안내 (사용자 직접 수행)

실제 브라우저 자동화는 로컬 에이전트에 위임하거나 사용자 직접 수행.
"""
from __future__ import annotations

from . import domain_assist  # noqa: F401
from .gates import (  # noqa: F401
    gate_gabia_public_read,
    gate_gabia_account_read,
    gate_gabia_login,
    gate_gabia_dns_change,
    gate_gabia_dns_delete,
    gate_gabia_domain_renew,
    gate_gabia_hosting_change,
    gate_gabia_payment,
    gate_gabia_credential_extract,
)
from .site_profile import GABIA_PROFILE  # noqa: F401
from .validators import validate_gabia_no_plain_secret  # noqa: F401

__status__ = {
    "tasks": {
        "status":  "read_only",
        "dns":     "read_only",
        "login":   "user_direct_required",
        "domain":  "approval_gated",
        "hosting": "approval_gated",
        "payment": "user_direct_required",
    },
    "note": (
        "Gabia: read tasks show gate policy. Write/change tasks require explicit approval. "
        "Login/payment/credential operations must be performed directly by the user."
    ),
}


def run_gabia(task: str, sub: str, args: list[str]) -> None:
    """Route Gabia site commands.

    task: status | dns | login | domain | hosting | payment
    """
    match task:
        case "status":
            _cmd_status()
        case "dns":
            _cmd_dns(sub or "read", args)
        case "login":
            _cmd_login()
        case "domain":
            _cmd_domain(sub or "info", args)
        case "domain-assist":
            _cmd_domain_assist(sub or "draft", args)
        case "hosting":
            _cmd_hosting(sub or "info", args)
        case "payment":
            _cmd_payment()
        case _:
            print(f"  [error] unknown gabia task: {task}")


def _cmd_status() -> None:
    result = gate_gabia_public_read()
    print("=" * 60)
    print("Gabia status (read-only)")
    print("=" * 60)
    print(f"gate: {result.gate_decision.value}")
    print(f"allowed: {result.allowed}")
    print("scope: domain expiry, service list (logged-in local agent required)")
    print("=" * 60)


def _cmd_dns(sub: str, args: list[str]) -> None:
    if sub in ("read", "list", "check"):
        result = gate_gabia_public_read()
        print("=" * 60)
        print("Gabia DNS read")
        print("=" * 60)
        print(f"gate: {result.gate_decision.value}")
        print(f"allowed: {result.allowed}")
        print("scope: dns.gabia.com 레코드 조회 (read-only)")
        print("=" * 60)
        return
    if sub in ("change", "update", "create"):
        result = gate_gabia_dns_change()
        print("=" * 60)
        print("Gabia DNS change (APPROVAL_REQUIRED)")
        print("=" * 60)
        print(f"gate: {result.gate_decision.value}")
        print(f"requires_approval: {result.requires_approval}")
        print("action: DNS 레코드 변경은 사용자 승인 후에만 실행 가능")
        print("=" * 60)
        return
    if sub in ("delete", "remove"):
        result = gate_gabia_dns_delete()
        print("=" * 60)
        print("Gabia DNS delete (APPROVAL_REQUIRED)")
        print("=" * 60)
        print(f"gate: {result.gate_decision.value}")
        print(f"requires_approval: {result.requires_approval}")
        print("action: DNS 레코드 삭제는 비가역 작업, 사용자 승인 후에만 실행 가능")
        print("=" * 60)
        return
    print(f"  [error] unknown gabia dns task: {sub}")


def _print_user_direct_gate(result, title: str, action: str, hint: str) -> None:
    """사용자 직접 수행 gate 결과 출력 공용(로그인·결제) — 제목·gate·blocked·안내 2줄."""
    print("=" * 60)
    print(title)
    print("=" * 60)
    print(f"gate: {result.gate_decision.value}")
    print(f"blocked: {result.is_blocked}")
    print(action)
    print(hint)
    print("=" * 60)


def _cmd_login() -> None:
    _print_user_direct_gate(
        gate_gabia_login(),
        "Gabia login (USER_DIRECT_REQUIRED)",
        "action: 가비아 로그인/OTP/2FA는 사용자가 직접 수행해야 합니다.",
        "  브라우저에서 accounts.gabia.com 접속 후 직접 로그인하세요.",
    )


def _cmd_domain(sub: str, args: list[str]) -> None:
    if sub in ("info", "list", "check"):
        result = gate_gabia_account_read()
        print("=" * 60)
        print("Gabia domain info (LOCAL_AGENT_REQUIRED)")
        print("=" * 60)
        print(f"gate: {result.gate_decision.value}")
        print("scope: domains.gabia.com 도메인 목록/상태 조회 (로그인 필요)")
        print("=" * 60)
        return
    if sub in ("renew", "transfer", "cancel"):
        result = gate_gabia_domain_renew()
        print("=" * 60)
        print(f"Gabia domain {sub} (APPROVAL_REQUIRED)")
        print("=" * 60)
        print(f"gate: {result.gate_decision.value}")
        print(f"requires_approval: {result.requires_approval}")
        print(f"action: 도메인 {sub}은 비가역 작업, 사용자 승인 후에만 실행 가능")
        print("=" * 60)
        return
    print(f"  [error] unknown gabia domain task: {sub}")


def _cmd_hosting(sub: str, args: list[str]) -> None:
    result = gate_gabia_hosting_change()
    print("=" * 60)
    print("Gabia hosting/mail setting (APPROVAL_REQUIRED)")
    print("=" * 60)
    print(f"gate: {result.gate_decision.value}")
    print(f"requires_approval: {result.requires_approval}")
    print("action: 호스팅/메일 설정 변경은 사용자 승인 후에만 실행 가능")
    print("=" * 60)


def _cmd_payment() -> None:
    _print_user_direct_gate(
        gate_gabia_payment(),
        "Gabia payment/billing (BLOCKED/USER_DIRECT_REQUIRED)",
        "action: 가비아 결제/청구/환불은 사용자가 직접 수행해야 합니다.",
        "  my.gabia.com/payment 에서 직접 처리하세요.",
    )


def _cmd_domain_assist(sub: str, args: list[str]) -> None:
    """도메인 개설 보조 — 초안 생성 및 gate 안내 (실제 등록 금지)."""
    if sub in ("draft", "plan", "summary"):
        raw = args[0] if args else ""
        if not raw:
            print("  [error] domain-assist draft requires a domain candidate argument")
            return
        validated = domain_assist.normalize_domain_candidate(raw)
        gate = domain_assist.evaluate_domain_registration_gate("draft")
        print("=" * 60)
        print("Gabia domain-assist: 도메인 등록 초안 (DRAFT ONLY)")
        print("=" * 60)
        print(f"입력: {raw}")
        print(f"정규화: {validated['normalized']}")
        print(f"유효: {validated['ok']}")
        if validated["errors"]:
            for e in validated["errors"]:
                print(f"  오류: {e}")
        if validated["warnings"]:
            for w in validated["warnings"]:
                print(f"  경고: {w}")
        print(f"gate: {gate['decision']}")
        print("최종 등록/결제/DNS 변경: USER_DIRECT_REQUIRED (사용자 직접 수행)")
        print("=" * 60)
        return
    if sub in ("gate", "check"):
        action = args[0] if args else "draft"
        gate = domain_assist.evaluate_domain_registration_gate(action)
        print("=" * 60)
        print(f"Gabia domain-assist gate: {action}")
        print("=" * 60)
        print(f"decision: {gate['decision']}")
        print(f"requires_approval: {gate['requires_approval']}")
        print(f"blocked: {gate['is_blocked_or_restricted']}")
        print(f"note: {gate['note']}")
        print("=" * 60)
        return
    print(f"  [error] unknown domain-assist sub: {sub}")
