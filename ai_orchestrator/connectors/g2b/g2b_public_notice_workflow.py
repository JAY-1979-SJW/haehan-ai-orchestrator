"""
G2B 공개 공고 Read-Only 워크플로우

g2b_domain_policy.py 기반으로 G2B 공개 공고 URL을 분류하고,
허용된 경우에만 open/read/navigate 계획을 생성한다.

이번 구현 범위:
- 공개 read-only workflow plan 생성까지
- click/type/fill/submit/download 자동 실행 구현 없음
- 로그인/인증/입찰/계약/결제 경로 BLOCK 유지
- task_executor/browser_worker live dispatch 없음
- wildcard 도메인 허용 없음
- DB write 없음
- safe_to_execute 항상 False
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.connectors.g2b.g2b_domain_policy import (
    DOMAIN_G2B_PUBLIC_READONLY,
    DOMAIN_NEEDS_URL_VERIFICATION,
    DOMAIN_READONLY_CANDIDATE,
    PATH_BLOCKED_BID_SUBMIT,
    PATH_BLOCKED_CERT,
    PATH_BLOCKED_CONTRACT,
    PATH_BLOCKED_LOGIN,
    PATH_BLOCKED_PAYMENT,
    PATH_DOWNLOAD_MANUAL_ONLY,
    classify_g2b_url,
    normalize_g2b_domain,
)

logger = logging.getLogger(__name__)

# ── verdict 값 ────────────────────────────────────────────────────────────────

VERDICT_ALLOWED = "ALLOWED"
VERDICT_BLOCKED = "BLOCKED"
VERDICT_NEEDS_VERIFICATION = "NEEDS_VERIFICATION"

# ── 허용 operation ────────────────────────────────────────────────────────────

ALLOWED_OPERATIONS: list[str] = ["read", "navigate", "open_url"]

# ── 금지 operation ────────────────────────────────────────────────────────────

FORBIDDEN_OPERATIONS: list[str] = [
    "submit",
    "type",
    "fill",
    "click",
    "click_submit",
    "download",
    "upload",
    "post",
    "write",
    "delete",
    "update",
    "login",
    "cert",
    "payment",
    "contract_submit",
    "bid_submit",
    "auto_login",
]

# ── workflow_steps 금지 step ──────────────────────────────────────────────────

_FORBIDDEN_WORKFLOW_STEPS: frozenset[str] = frozenset(
    {
        "click",
        "type",
        "fill",
        "submit",
        "download",
        "login",
        "cert",
        "payment",
        "contract_submit",
        "bid_submit",
        "auto_login",
        "upload",
        "write_form",
    }
)

# ── 공개 read-only workflow 계획 ──────────────────────────────────────────────

_READONLY_WORKFLOW_STEPS: list[dict[str, str]] = [
    {"step": "normalize_url", "mode": "read_only"},
    {"step": "classify_domain", "mode": "read_only"},
    {"step": "preflight_policy", "mode": "read_only"},
    {"step": "open_url", "mode": "read_only"},
    {"step": "read_public_notice", "mode": "read_only"},
]

_NAVIGATE_WORKFLOW_STEPS: list[dict[str, str]] = [
    {"step": "normalize_url", "mode": "read_only"},
    {"step": "classify_domain", "mode": "read_only"},
    {"step": "preflight_policy", "mode": "read_only"},
    {"step": "navigate_to_url", "mode": "read_only"},
]

_OPEN_URL_WORKFLOW_STEPS: list[dict[str, str]] = [
    {"step": "normalize_url", "mode": "read_only"},
    {"step": "classify_domain", "mode": "read_only"},
    {"step": "preflight_policy", "mode": "read_only"},
    {"step": "open_url", "mode": "read_only"},
]


def _build_canonical_url(original_url: str, normalized_domain: str) -> str:
    """www 도메인을 apex로 정규화한 canonical URL 반환."""
    if not original_url or not normalized_domain:
        return original_url or ""
    try:
        parsed = urlparse(original_url)
        if parsed.netloc and parsed.netloc.lower() != normalized_domain:
            return original_url.replace(parsed.netloc, normalized_domain, 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("G2B 공고 URL 도메인 치환 실패(무시): %s", type(exc).__name__)
        pass
    return original_url


def _get_workflow_steps(operation: str) -> list[dict[str, str]]:
    op = (operation or "").lower().strip()
    if op == "navigate":
        return list(_NAVIGATE_WORKFLOW_STEPS)
    if op == "open_url":
        return list(_OPEN_URL_WORKFLOW_STEPS)
    return list(_READONLY_WORKFLOW_STEPS)


def classify_g2b_public_notice_workflow_request(
    url: str,
    operation: str,
) -> dict[str, Any]:
    """
    G2B 공개 공고 워크플로우 요청을 분류한다.

    g2b_domain_policy.classify_g2b_url()을 재사용하고
    workflow 관점의 추가 판정을 수행한다.

    반환:
    - input_url
    - normalized_domain
    - canonical_url
    - operation
    - domain_classification
    - path_decision
    - compliance_decision
    - readonly_allowed
    - download_auto_allowed (항상 False)
    - blocked_reason
    - workflow_steps
    - allowed_operations
    - forbidden_operations
    - requires_url_verification
    - verdict
    - safe_to_execute (항상 False)
    - message_ko
    """
    op = (operation or "").lower().strip()

    base_result: dict[str, Any] = {
        "input_url": url,
        "normalized_domain": "",
        "canonical_url": url or "",
        "operation": op,
        "domain_classification": "",
        "path_decision": "",
        "compliance_decision": "BLOCK",
        "readonly_allowed": False,
        "download_auto_allowed": False,
        "blocked_reason": "",
        "workflow_steps": [],
        "allowed_operations": ALLOWED_OPERATIONS,
        "forbidden_operations": FORBIDDEN_OPERATIONS,
        "requires_url_verification": False,
        "verdict": VERDICT_BLOCKED,
        "safe_to_execute": False,
        "message_ko": "",
    }

    # 금지 operation 즉시 차단
    if op in FORBIDDEN_OPERATIONS:
        base_result["blocked_reason"] = f"FORBIDDEN_OPERATION: {op}"
        base_result["message_ko"] = f"operation '{op}'은 G2B 공개 공고 워크플로우에서 허용되지 않습니다."
        if op == "download":
            base_result["path_decision"] = PATH_DOWNLOAD_MANUAL_ONLY
        return base_result

    # 허용 operation 아닌 경우
    if op not in ALLOWED_OPERATIONS:
        base_result["blocked_reason"] = f"UNKNOWN_OPERATION: {op}"
        base_result["message_ko"] = f"알 수 없는 operation: '{op}'"
        return base_result

    # g2b_domain_policy 분류 재사용
    domain_result = classify_g2b_url(url, operation_type=op)

    # 도메인 정규화 정보
    try:
        parsed = urlparse(url) if url else None
        raw_domain = parsed.netloc if parsed else ""
    except Exception:  # noqa: BLE001 - 나라장터 공고 URL 도메인 정규화 -- urlparse 실패 시 원본 URL을 그대로 반환하는 안전한 폴백, 쓰기 없음
        raw_domain = ""
    domain_info = normalize_g2b_domain(raw_domain)  # noqa: F841

    normalized_domain = domain_result.get("normalized_domain", "")
    base_result["normalized_domain"] = normalized_domain
    base_result["canonical_url"] = _build_canonical_url(url, normalized_domain)
    base_result["domain_classification"] = domain_result.get("domain_decision", "")
    base_result["path_decision"] = domain_result.get("path_decision", "")
    base_result["requires_url_verification"] = domain_result.get("needs_url_verification", False)

    # 검증 필요 도메인
    if domain_result.get("domain_decision") in (DOMAIN_NEEDS_URL_VERIFICATION, DOMAIN_READONLY_CANDIDATE):
        base_result["verdict"] = VERDICT_NEEDS_VERIFICATION
        base_result["blocked_reason"] = domain_result.get("blocked_reason", "NEEDS_URL_VERIFICATION")
        base_result["message_ko"] = domain_result.get("message_ko", "")
        return base_result

    # 비 G2B 도메인
    if domain_result.get("domain_decision") == "NOT_G2B":
        base_result["blocked_reason"] = "NOT_G2B_DOMAIN"
        base_result["message_ko"] = domain_result.get("message_ko", "G2B 도메인 아님.")
        return base_result

    # operation 승인 필요
    if domain_result.get("operation_decision") == "REQUIRES_APPROVAL":
        base_result["blocked_reason"] = f"OPERATION_REQUIRES_APPROVAL: {op}"
        base_result["message_ko"] = f"operation '{op}'은 별도 승인이 필요합니다."
        return base_result

    # 경로 차단
    path_decision = domain_result.get("path_decision", "")
    _blocked_paths = {
        PATH_BLOCKED_LOGIN,
        PATH_BLOCKED_CERT,
        PATH_BLOCKED_BID_SUBMIT,
        PATH_BLOCKED_CONTRACT,
        PATH_BLOCKED_PAYMENT,
    }
    if path_decision in _blocked_paths:
        base_result["blocked_reason"] = domain_result.get("blocked_reason", f"PATH_BLOCKED: {path_decision}")
        base_result["message_ko"] = domain_result.get("message_ko", f"경로 차단: {path_decision}")
        return base_result

    # 공개 read-only 허용
    if domain_result.get("readonly_allowed") and domain_result.get("domain_decision") == DOMAIN_G2B_PUBLIC_READONLY:
        steps = _get_workflow_steps(op)
        base_result["compliance_decision"] = "ALLOW_BROWSER_READONLY"
        base_result["readonly_allowed"] = True
        base_result["workflow_steps"] = steps
        base_result["verdict"] = VERDICT_ALLOWED
        base_result["message_ko"] = f"G2B 공개 공고 read-only 워크플로우 허용. operation={op}"
        return base_result

    # 기타 차단
    base_result["blocked_reason"] = domain_result.get("blocked_reason", "POLICY_BLOCK")
    base_result["message_ko"] = domain_result.get("message_ko", "정책에 의해 차단.")
    return base_result


def build_g2b_public_notice_workflow(
    url: str,
    operation: str = "read",
) -> dict[str, Any]:
    """
    G2B 공개 공고 read-only 워크플로우를 빌드한다.

    classify_g2b_public_notice_workflow_request()를 호출하고
    결과를 반환한다.

    실제 브라우저 실행, task_executor dispatch, DB write 없음.
    """
    return classify_g2b_public_notice_workflow_request(url, operation)


def validate_g2b_public_notice_workflow_result(result: dict[str, Any]) -> list[str]:
    """
    워크플로우 결과 필수 필드 및 정책 준수를 검증한다.

    반환: 오류 목록 (빈 목록 = 유효)
    """
    errors: list[str] = []

    required_fields = [
        "input_url",
        "normalized_domain",
        "canonical_url",
        "operation",
        "domain_classification",
        "compliance_decision",
        "readonly_allowed",
        "download_auto_allowed",
        "blocked_reason",
        "workflow_steps",
        "allowed_operations",
        "forbidden_operations",
        "requires_url_verification",
        "verdict",
        "safe_to_execute",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    if result.get("download_auto_allowed") is not False:
        errors.append("download_auto_allowed는 항상 False여야 한다")

    # workflow_steps에 금지 step 포함 여부
    for step_entry in result.get("workflow_steps", []):
        step_name = (step_entry.get("step") or "").lower()
        if step_name in _FORBIDDEN_WORKFLOW_STEPS:
            errors.append(f"workflow_steps에 금지 step 포함: {step_name}")

    # allowed_operations에 금지 동작 포함 여부
    for op in result.get("allowed_operations", []):
        if op.lower() in {f.lower() for f in FORBIDDEN_OPERATIONS}:
            errors.append(f"allowed_operations에 금지 동작 포함: {op}")

    valid_verdicts = {VERDICT_ALLOWED, VERDICT_BLOCKED, VERDICT_NEEDS_VERIFICATION}
    if "verdict" in result and result["verdict"] not in valid_verdicts:
        errors.append(f"유효하지 않은 verdict: {result['verdict']}")

    return errors


__all__ = [
    "ALLOWED_OPERATIONS",
    "FORBIDDEN_OPERATIONS",
    "VERDICT_ALLOWED",
    "VERDICT_BLOCKED",
    "VERDICT_NEEDS_VERIFICATION",
    "build_g2b_public_notice_workflow",
    "classify_g2b_public_notice_workflow_request",
    "validate_g2b_public_notice_workflow_result",
]
