"""Gabia 도메인 개설 보조 모듈.

허용 범위:
  - 도메인 후보 정규화/검증
  - 신청 초안 데이터 생성
  - DNS 기본값 초안 생성
  - 사용자 검토용 요약 생성
  - 최종 실행은 반드시 USER_DIRECT_REQUIRED 반환

금지 범위:
  - 실제 Gabia 로그인/브라우저 호출 금지
  - 실제 도메인 등록/결제/약관 동의 submit 금지
  - 실제 DNS 변경 금지
  - session/cookie/encrypted_bundle 접근 금지
  - data/sessions/*.json 읽기 금지
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# 허용 TLD 목록 (예시 — 실제 가용 여부는 local-agent가 확인)
SUPPORTED_TLDS = {
    ".kr", ".com", ".net", ".org", ".co.kr", ".or.kr", ".pe.kr",
    ".io", ".dev", ".app", ".ai", ".biz", ".info",
}

# 도메인명 허용 문자 패턴 (하이픈 허용, 시작/끝 하이픈 금지)
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$")

# session/cookie 파일 경로 — 이 모듈에서 절대 접근하지 않음 (참고용 상수)
_FORBIDDEN_SESSION_PATHS = [
    "data/sessions/gabia.com.json",
    "data/sessions/my.gabia.com.json",
    "data/sessions/www.gabia.com.json",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 1. 도메인 후보 정규화 ────────────────────────────────────────────────────

def normalize_domain_candidate(raw: str) -> dict[str, Any]:
    """도메인 후보를 정규화하고 검증 결과를 반환한다.

    반환:
        ok: bool
        normalized: str  (정규화된 도메인, TLD 포함)
        label: str       (TLD 제외 레이블)
        tld: str         (검출된 TLD)
        errors: list[str]
        warnings: list[str]
    """
    errors: list[str] = []
    warnings: list[str] = []

    # protocol, path, whitespace 제거
    cleaned = raw.strip().lower()
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = re.sub(r"^www\.", "", cleaned)
    cleaned = cleaned.split("/")[0].split("?")[0].split("#")[0].strip()

    if not cleaned:
        return {"ok": False, "normalized": "", "label": "", "tld": "", "errors": ["빈 입력"], "warnings": []}

    # TLD 분리
    tld = ""
    label = cleaned
    # 긴 TLD부터 매칭 (co.kr 우선)
    for candidate_tld in sorted(SUPPORTED_TLDS, key=len, reverse=True):
        if cleaned.endswith(candidate_tld):
            label = cleaned[: -len(candidate_tld)]
            tld = candidate_tld
            break

    if not tld:
        warnings.append(f"TLD를 감지할 수 없음 — 기본값 .kr 또는 사용자 지정 필요 (입력: '{cleaned}')")
        label = cleaned
        tld = ""

    # 레이블 유효성 검사
    if not label:
        errors.append("도메인 레이블이 비어 있음")
    elif len(label) < 2:
        errors.append(f"도메인 레이블이 너무 짧음 (최소 2자): '{label}'")
    elif len(label) > 63:
        errors.append(f"도메인 레이블이 너무 길음 (최대 63자): '{label}'")
    elif not _DOMAIN_LABEL_RE.match(label):
        errors.append(f"허용되지 않는 문자 또는 형식: '{label}' (영문 소문자, 숫자, 하이픈만 허용, 시작/끝 하이픈 금지)")

    # 한글 감지 경고
    if re.search(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", raw):
        warnings.append("한글 도메인 입력 감지 — punycode 변환이 필요할 수 있음 (실제 변환은 local-agent에서 수행)")

    normalized = f"{label}{tld}" if tld else label
    return {
        "ok": not errors,
        "normalized": normalized,
        "label": label,
        "tld": tld,
        "errors": errors,
        "warnings": warnings,
    }


# ── 2. TLD 후보 목록 생성 ────────────────────────────────────────────────────

def suggest_tld_candidates(label: str) -> list[dict[str, Any]]:
    """레이블에 대해 등록 검토 가능한 TLD 후보 목록을 반환한다.

    실제 가용 여부는 local-agent 또는 사용자가 확인해야 함.
    """
    candidates = []
    for tld in sorted(SUPPORTED_TLDS):
        candidates.append({
            "domain": f"{label}{tld}",
            "tld": tld,
            "availability": "CHECK_REQUIRED",  # 실제 조회는 local-agent
            "note": "가비아 도메인 검색에서 직접 확인 필요",
        })
    return candidates


# ── 3. 신청 초안 생성 ────────────────────────────────────────────────────────

def build_domain_registration_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """도메인 등록 신청 초안을 생성한다.

    최종 등록/결제/약관 동의는 USER_DIRECT_REQUIRED로 고정.
    실제 availability는 UNKNOWN / CHECK_REQUIRED 반환.
    """
    domain = payload.get("domain", "")
    tld = payload.get("tld", "")
    years = payload.get("years", 1)
    owner_type = payload.get("owner_type", "individual")
    admin_contact = payload.get("admin_contact", {})
    dns_mode = payload.get("dns_mode", "gabia_dns")
    nameserver_mode = payload.get("nameserver_mode", "gabia_default")
    privacy_option = payload.get("privacy_option", True)
    auto_renew_option = payload.get("auto_renew_option", False)

    return {
        "generated_at": _now(),
        "draft_type": "domain_registration",
        "domain": domain,
        "tld": tld,
        "full_domain": f"{domain}{tld}" if domain and tld else domain,
        "registration_years": max(1, min(int(years), 10)),
        "owner_type": owner_type,
        "admin_contact": {
            "name": admin_contact.get("name", ""),
            "email": admin_contact.get("email", ""),
            "phone": admin_contact.get("phone", ""),
        },
        "dns_mode": dns_mode,
        "nameserver_mode": nameserver_mode,
        "privacy_proxy_requested": bool(privacy_option),
        "auto_renew_requested": bool(auto_renew_option),
        "availability": "CHECK_REQUIRED",
        "payment_required": True,
        "final_action": "USER_DIRECT_REQUIRED",
        "final_action_url": "https://my.gabia.com/service#/?carve_code=domain",
        "note": (
            "이 초안은 검토용입니다. "
            "최종 등록/결제/약관 동의는 사용자가 가비아 사이트에서 직접 수행해야 합니다."
        ),
        "gate_policy": {
            "search_check": "LOCAL_AGENT_REQUIRED",
            "draft": "ALLOWED",
            "apply_dns": "APPROVAL_REQUIRED + USER_DIRECT_REQUIRED",
            "final_register": "USER_DIRECT_REQUIRED",
            "payment": "USER_DIRECT_REQUIRED",
            "login_session_cookie": "BLOCKED",
        },
    }


# ── 4. DNS 기본값 초안 생성 ──────────────────────────────────────────────────

def build_dns_default_draft(
    domain: str,
    server_ip: str = "",
    mail_provider: str = "hiworks",
) -> dict[str, Any]:
    """DNS 기본값 초안을 생성한다.

    기존 haehan-ai.kr 설정을 참고 템플릿으로 사용.
    실제 DNS 적용은 APPROVAL_REQUIRED + USER_DIRECT_REQUIRED.
    """
    records: list[dict[str, Any]] = []

    if server_ip:
        records += [
            {"type": "A", "host": "@", "value": server_ip, "ttl": 3600, "note": "루트 도메인"},
            {"type": "A", "host": "www", "value": server_ip, "ttl": 3600, "note": "www"},
            {"type": "A", "host": "app", "value": server_ip, "ttl": 600, "note": "앱 서버"},
            {"type": "A", "host": "api", "value": server_ip, "ttl": 600, "note": "API 서버"},
        ]
    else:
        records.append({
            "type": "A", "host": "@", "value": "SERVER_IP_REQUIRED",
            "ttl": 3600, "note": "서버 IP를 지정해야 함",
        })

    if mail_provider == "hiworks":
        records += [
            {"type": "MX", "host": "@", "value": "mailapp.hiworks.co.kr.", "ttl": 600, "priority": 10, "note": "Hiworks 메일"},
            {"type": "TXT", "host": "@", "value": "v=spf1 include:_spf.hiworks.co.kr ~all", "ttl": 600, "note": "Hiworks SPF"},
            {"type": "CNAME", "host": "mail", "value": "mailapp.hiworks.co.kr.", "ttl": 600, "note": "메일 CNAME"},
            {"type": "CNAME", "host": "hiworks", "value": "hiworksapp.hiworks.co.kr.", "ttl": 600, "note": "Hiworks CNAME"},
        ]
    elif mail_provider == "google":
        records += [
            {"type": "MX", "host": "@", "value": "aspmx.l.google.com.", "ttl": 600, "priority": 1, "note": "Google Workspace MX"},
            {"type": "TXT", "host": "@", "value": "v=spf1 include:_spf.google.com ~all", "ttl": 600, "note": "Google SPF"},
        ]

    records.append({
        "type": "TXT", "host": "_dmarc",
        "value": "v=DMARC1; p=none; rua=mailto:dmarc@" + domain,
        "ttl": 600, "note": "DMARC 기본값 (p=none, 모니터링 모드)",
    })

    return {
        "generated_at": _now(),
        "draft_type": "dns_default",
        "domain": domain,
        "mail_provider": mail_provider,
        "records": records,
        "final_action": "APPROVAL_REQUIRED + USER_DIRECT_REQUIRED",
        "note": (
            "이 초안은 검토용입니다. "
            "실제 DNS 적용은 가비아 DNS 관리 화면에서 사용자가 직접 수행해야 합니다. "
            "잘못된 DNS 변경은 웹사이트/메일 장애를 유발할 수 있습니다."
        ),
    }


# ── 5. 사용자 검토용 요약 생성 ───────────────────────────────────────────────

def build_registration_summary(
    domain_result: dict[str, Any],
    draft: dict[str, Any],
    dns_draft: dict[str, Any],
) -> dict[str, Any]:
    """신청 초안 전체를 사용자 검토용 요약으로 정리한다."""
    return {
        "generated_at": _now(),
        "summary_type": "gabia_domain_registration_assist",
        "domain_validation": domain_result,
        "registration_draft": draft,
        "dns_default_draft": dns_draft,
        "actions_required": [
            "1. 가비아 도메인 검색에서 가용 여부 확인",
            "2. 신청자/관리자/기술담당자 정보 입력",
            "3. 결제 수단 확인",
            "4. 약관 동의 후 최종 등록 (사용자 직접 수행)",
            "5. DNS 레코드 적용 (승인 후 사용자 직접 수행)",
        ],
        "blocked_actions": [
            "자동 로그인 금지",
            "session/cookie 자동 재사용 금지",
            "결제 자동 실행 금지",
            "약관 자동 동의 금지",
            "DNS 자동 변경 금지",
        ],
    }


# ── 6. gate 판단 ─────────────────────────────────────────────────────────────

def evaluate_domain_registration_gate(action: str) -> dict[str, Any]:
    """도메인 개설 단계별 gate 판단 결과를 반환한다."""
    _GATE_MAP = {
        "search":            ("LOCAL_AGENT_REQUIRED", False, False),
        "check":             ("LOCAL_AGENT_REQUIRED", False, False),
        "draft":             ("ALLOWED",              False, False),
        "summary":           ("ALLOWED",              False, False),
        "apply_dns":         ("APPROVAL_REQUIRED",    True,  True),
        "final_register":    ("USER_DIRECT_REQUIRED", False, True),
        "payment":           ("USER_DIRECT_REQUIRED", False, True),
        "login":             ("BLOCKED",              False, True),
        "session":           ("BLOCKED",              False, True),
        "cookie":            ("BLOCKED",              False, True),
        "password":          ("BLOCKED",              False, True),
        "otp":               ("BLOCKED",              False, True),
        "credential_extract":("BLOCKED",              False, True),
    }
    decision, requires_approval, is_blocked_or_restricted = _GATE_MAP.get(
        action, ("UNKNOWN_ACTION", False, False)
    )
    return {
        "action": action,
        "decision": decision,
        "requires_approval": requires_approval,
        "is_blocked_or_restricted": is_blocked_or_restricted,
        "note": "final_register/payment/dns_apply는 사용자 직접 수행 필수",
    }
