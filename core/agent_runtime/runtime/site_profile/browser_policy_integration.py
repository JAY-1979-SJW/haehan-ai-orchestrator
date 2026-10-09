"""Browser Policy Integration — opt-in wrapper for existing browser actions.

LOCAL_BROWSER_POLICY_SAFE_EXPANSION 후속 작업
(BROWSER_ACTION_SAFE_EXPANSION_OPTIN_INTEGRATION_1).

기본값(use_policy_registry=False)은 기존 액션 그대로 위임 — backward compatible.
use_policy_registry=True일 때만 site/value/selector/preflight 정책 검증 수행.
"""

from __future__ import annotations

from typing import Any

from core.agent_runtime.runtime.site_profile.browser_allowlist_expansion_preflight import (
    VERDICT_BLOCKED,
    can_auto_approve,
    preflight_expansion,
)
from core.agent_runtime.runtime.site_profile.browser_discovery_candidates import (
    CANDIDATE_DESTRUCTIVE_BUTTON,
    CANDIDATE_DOWNLOAD_LINK,
    CANDIDATE_FILE_INPUT,
    CANDIDATE_SUBMIT_BUTTON,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    is_forbidden_label,
)
from core.agent_runtime.runtime.site_profile.browser_site_registry import (
    EXECUTION_LOCAL_AGENT_REQUIRED,
    get_site,
    resolve_url,
    validate_raw_url,
)
from core.agent_runtime.runtime.site_profile.browser_value_registry import (
    is_forbidden_value,
    resolve_value_for_field,
)

POLICY_FLAG = "use_policy_registry"

_DESTRUCTIVE_KEYWORDS = (
    "submit",
    "save",
    "sign",
    "delete",
    "payment",
    "bid",
    "transfer",
    "withdraw",
    "approve",
    "confirm",
    "제출",
    "저장",
    "삭제",
    "전자서명",
    "투찰",
    "결제",
    "송금",
    "이체",
    "출금",
    "확정",
    "상신",
)


def _verdict(ok: bool, verdict: str, reason: str = "", **extra) -> dict[str, Any]:
    return {
        "ok": ok,
        "policy_verdict": verdict,
        "policy_reason": reason,
        **extra,
    }


def _is_destructive_label(label: str) -> bool:
    if not label:
        return False
    low = label.lower()
    return any(kw in low or kw in label for kw in _DESTRUCTIVE_KEYWORDS)


def _normalize_kwargs(kwargs: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """opt-in flag 추출 후 나머지 인자 분리."""
    opted_in = bool(kwargs.pop(POLICY_FLAG, False))
    return opted_in, kwargs


def open_with_policy(
    *,
    site_id: str | None = None,
    path_key: str = "/",
    raw_url: str | None = None,
    intended_purpose: str = "readonly_browse",
    **kwargs,
) -> dict[str, Any]:
    """browser.open opt-in 검증.

    - use_policy_registry=False (기본): legacy ok 패스스루
    - True: site_id 또는 등록된 raw_url만 허용
    """
    opted_in, kwargs = _normalize_kwargs(kwargs)
    if not opted_in:
        return _verdict(True, "LEGACY_BYPASS", "use_policy_registry=False — 기존 동작")

    if not site_id and not raw_url:
        return _verdict(False, "BLOCKED", "site_id 또는 등록된 raw_url 필수")

    if raw_url and not site_id:
        url_check = validate_raw_url(raw_url)
        if not url_check.get("ok"):
            return _verdict(False, "BLOCKED", f"raw URL 차단: {url_check.get('error')}")
        site_id = url_check["site_id"]

    if not site_id:  # fail-closed: site_id 확정 불가면 차단 (정상 경로에선 도달 불가)
        return _verdict(False, "BLOCKED", "site_id 확인 불가")

    site = get_site(site_id)
    if site is None:
        return _verdict(False, "BLOCKED", f"site_id 미등록: {site_id}")
    if site.execution_location != EXECUTION_LOCAL_AGENT_REQUIRED:
        return _verdict(False, "BLOCKED", "execution_location 정책 위반")

    resolved = resolve_url(site_id, path_key)
    if not resolved.get("ok"):
        return _verdict(False, "BLOCKED", resolved.get("error", "path 차단"), verdict_detail=resolved.get("verdict"))

    pre = preflight_expansion(
        site_candidate={"site_id": site_id},
        intended_purpose=intended_purpose,
    )
    if pre["verdict"] == VERDICT_BLOCKED:
        return _verdict(False, "BLOCKED", pre["reason"])

    return _verdict(
        True,
        "ALLOWED",
        "site policy 검증 통과",
        site_id=site_id,
        path_key=path_key,
        execution_location=site.execution_location,
    )


def type_with_policy(
    *,
    selector_key: str | None = None,
    value_key: str | None = None,
    raw_text: str | None = None,
    field_id: str = "",
    business_profile: str = "",
    **kwargs,
) -> dict[str, Any]:
    """browser.type opt-in 검증.

    - True 모드에서 raw_text/raw selector 직접 입력 차단.
    - value_key + selector_key 조합만 허용.
    """
    opted_in, kwargs = _normalize_kwargs(kwargs)
    if not opted_in:
        return _verdict(True, "LEGACY_BYPASS", "use_policy_registry=False — 기존 동작")

    if raw_text is not None:
        forbidden, reason = is_forbidden_value(str(raw_text), field_id)
        if forbidden:
            return _verdict(False, "BLOCKED", f"raw text 차단: {reason}")
        return _verdict(False, "BLOCKED", "raw text 입력 직접 실행 금지 — value_key 사용 필요")

    if not selector_key:
        return _verdict(False, "BLOCKED", "selector_key 필수 — raw selector 차단")

    if not value_key:
        return _verdict(False, "BLOCKED", "value_key 필수")

    val = resolve_value_for_field(value_key, field_id, business_profile)
    if not val.get("ok"):
        return _verdict(False, "BLOCKED", f"value 정책 위반: {val.get('verdict')}")

    return _verdict(
        True,
        "ALLOWED",
        "value policy 검증 통과",
        selector_key=selector_key,
        value_key=value_key,
        sample_safe_value=val["sample_safe_value"],
    )


def submit_with_policy(
    *,
    selector_key: str | None = None,
    selector_label: str = "",
    candidate_type: str = CANDIDATE_SUBMIT_BUTTON,
    approval_token: str | None = None,
    business_profile: str = "",
    **kwargs,
) -> dict[str, Any]:
    """browser.submit opt-in 검증.

    - submit/save/sign/delete/payment/bid 후보 = HIGH risk
    - approval_token 없으면 차단
    """
    opted_in, kwargs = _normalize_kwargs(kwargs)
    if not opted_in:
        return _verdict(True, "LEGACY_BYPASS", "use_policy_registry=False — 기존 동작")

    if not selector_key:
        return _verdict(False, "BLOCKED", "selector_key 필수 — raw selector 차단")

    is_destructive = candidate_type in (CANDIDATE_SUBMIT_BUTTON, CANDIDATE_DESTRUCTIVE_BUTTON) or _is_destructive_label(
        selector_label
    )

    if is_destructive and not approval_token:
        return _verdict(
            False,
            "BLOCKED",
            "destructive/submit selector — approval_token 필수",
            risk_level=RISK_HIGH,
            required_approval=True,
        )

    selector_candidate = {
        "candidate_type": candidate_type,
        "visible_label": selector_label,
        "role": "button",
        "selector_fingerprint": selector_key,
        "risk_hint": RISK_HIGH if is_destructive else RISK_MEDIUM,
        "confidence": "MEDIUM",
    }
    pre = preflight_expansion(
        selector_candidate=selector_candidate,
        business_profile=business_profile,
    )
    if pre["verdict"] == VERDICT_BLOCKED:
        return _verdict(False, "BLOCKED", pre["reason"])

    return _verdict(
        True,
        "REVIEW_OR_HANDOFF" if is_destructive else "ALLOWED",
        pre["reason"],
        risk_level=pre["risk_level"],
        required_approval=pre["required_approval"],
        handoff_required=is_destructive,
        approval_status="APPROVED" if approval_token else "NONE",
    )


def download_with_policy(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    *,
    source_url: str | None = None,
    site_id: str | None = None,
    path_key: str = "/",
    candidate_type: str = CANDIDATE_DOWNLOAD_LINK,
    selector_label: str = "",
    expected_extension: str = "",
    intended_purpose: str = "readonly_download",
    **kwargs,
) -> dict[str, Any]:
    """browser.download_file opt-in 검증.

    - read-only download_link_candidate는 LOW risk
    - cookie/session 추출 금지, 로그인 우회 금지
    """
    opted_in, kwargs = _normalize_kwargs(kwargs)
    if not opted_in:
        return _verdict(True, "LEGACY_BYPASS", "use_policy_registry=False — 기존 동작")

    if source_url and not site_id:
        url_check = validate_raw_url(source_url)
        if not url_check.get("ok"):
            return _verdict(False, "BLOCKED", f"raw URL 차단: {url_check.get('error')}")
        site_id = url_check["site_id"]

    if not site_id:
        return _verdict(False, "BLOCKED", "site_id 또는 등록된 source_url 필수")

    if is_forbidden_label(selector_label):
        return _verdict(False, "BLOCKED", f"민감 라벨 차단: {selector_label}")

    selector_candidate = {
        "candidate_type": candidate_type,
        "visible_label": selector_label or "download",
        "role": "link",
        "selector_fingerprint": "download_safe_fp",
        "risk_hint": RISK_LOW,
        "confidence": "MEDIUM",
    }
    pre = preflight_expansion(
        selector_candidate=selector_candidate,
        intended_purpose=intended_purpose,
    )
    if pre["verdict"] == VERDICT_BLOCKED:
        return _verdict(False, "BLOCKED", pre["reason"])

    return _verdict(
        True,
        "ALLOWED",
        "read-only download 정책 통과",
        site_id=site_id,
        expected_extension=expected_extension,
        auto_approve=can_auto_approve(pre),
    )


def attach_with_policy(
    *,
    site_id: str | None = None,
    file_basename: str = "",
    selector_label: str = "",
    approval_token: str | None = None,
    submit_after_attach: bool = False,
    **kwargs,
) -> dict[str, Any]:
    """browser.attach_file opt-in 검증.

    - attach 자체는 USER_DELEGATED/HIGH risk
    - submit_after_attach=True는 추가 차단 (실제 제출 금지)
    - file_path는 basename만 허용 (path traversal 차단)
    """
    opted_in, kwargs = _normalize_kwargs(kwargs)
    if not opted_in:
        return _verdict(True, "LEGACY_BYPASS", "use_policy_registry=False — 기존 동작")

    if not site_id or not get_site(site_id):
        return _verdict(False, "BLOCKED", "site_id 미등록")

    if not file_basename:
        return _verdict(False, "BLOCKED", "file_basename 필수")
    if "/" in file_basename or "\\" in file_basename or ".." in file_basename:
        return _verdict(False, "BLOCKED", "file path traversal 시도 — basename만 허용")

    if submit_after_attach:
        return _verdict(False, "BLOCKED", "submit_after_attach 차단 — attach와 submit은 분리 승인")

    if not approval_token:
        return _verdict(
            False, "BLOCKED", "attach 실행 — approval_token 필수", risk_level=RISK_HIGH, required_approval=True
        )

    selector_candidate = {
        "candidate_type": CANDIDATE_FILE_INPUT,
        "visible_label": selector_label or "attach",
        "role": "file",
        "selector_fingerprint": "attach_fp",
        "risk_hint": RISK_MEDIUM,
        "confidence": "MEDIUM",
    }
    pre = preflight_expansion(selector_candidate=selector_candidate)
    if pre["verdict"] == VERDICT_BLOCKED:
        return _verdict(False, "BLOCKED", pre["reason"])

    return _verdict(
        True,
        "ALLOWED",
        "attach 정책 검증 통과 (approval 보유)",
        risk_level=RISK_MEDIUM,
        required_approval=True,
        file_basename=file_basename,
    )
