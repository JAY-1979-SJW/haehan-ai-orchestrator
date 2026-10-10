"""
G2B 기존 OpenAPI 앱 Bridge Adapter

기존 OpenAPI 앱이 수집한 공고 데이터를 현재 앱의 표준 candidate로 변환한다.

원칙:
- G2B OpenAPI 직접 호출 없음
- data.go.kr API key 읽기/저장 없음
- 기존 앱 DB 직접 접근 없음
- 기존 앱 수정 없음
- read-only HTTP GET 또는 파일 산출물 입력만 허용
- content validator/execution gate 우회 없음
- CONTENT_VALID_PASS 임의 생성 없음
- 쿠키/session/token/password/otp 저장 없음
- DB write 없음
- click/type/fill/submit/download 실행 없음
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# ── 고정 정책 필드 ─────────────────────────────────────────────────────────────

_BRIDGE_POLICY_FIXED: dict[str, Any] = {
    "api_key_used_by_current_app": False,
    "api_key_value_exposed": False,
    "db_read_direct": False,
    "db_write": False,
    "wildcard_domain_allowed": False,
    "download_auto_allowed": False,
    "click_type_fill_submit_blocked": True,
    "source": "existing_g2b_openapi_app",
}

# ── 허용 도메인 ────────────────────────────────────────────────────────────────

_ALLOWED_DOMAINS: frozenset[str] = frozenset({"g2b.go.kr", "www.g2b.go.kr"})
_NEEDS_VERIFICATION_DOMAINS: frozenset[str] = frozenset({"shop.g2b.go.kr", "api.g2b.go.kr"})

# ── 차단 경로 패턴 ─────────────────────────────────────────────────────────────

_BLOCKED_URL_PATTERNS: tuple[str, ...] = (
    "/login",
    "/cert",
    "/bid_submit",
    "/contract",
    "/payment",
    "/download",
    "/upload",
    "egovuserreqstlogin",
    "usercert",
    "ptb05001p",
    "ctb01001",
    "checkout",
    "ptb04001p",
    "downloadfile",
    "filedown",
    "attachdown",
)

# ── 필수 필드 ──────────────────────────────────────────────────────────────────

_REQUIRED_ITEM_FIELDS: tuple[str, ...] = ("bid_notice_no", "bid_notice_order", "notice_name")

# ── 기존 앱 필드 → 현재 앱 필드 mapping ──────────────────────────────────────

_FIELD_ALIASES: dict[str, str] = {
    "bidNtceNo": "bid_notice_no",
    "bidNtceOrd": "bid_notice_order",
    "bidNtceNm": "notice_name",
    "demandOrgNm": "demand_org",
    "ntceInsttNm": "notice_org",
    "bidBeginDt": "posted_at",
    "rgstDt": "posted_at",
    "bsnsDivNm": "business_type",
    "ntceDtlUrl": "detail_url",
}


def _classify_url(url: str) -> str:
    """URL을 safe/blocked/needs_verification/external로 분류한다."""
    if not url:
        return "missing"
    parsed = urlparse(url)
    netloc = parsed.netloc
    lower = url.lower()
    if netloc in _NEEDS_VERIFICATION_DOMAINS:
        return "needs_verification"
    if netloc not in _ALLOWED_DOMAINS:
        return "external"
    if any(p in lower for p in _BLOCKED_URL_PATTERNS):
        return "blocked"
    return "safe"


def normalize_existing_g2b_openapi_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    기존 OpenAPI 앱 공고 item을 현재 앱 표준 필드로 정규화한다.

    camelCase 필드명(기존 앱 응답)과 snake_case 필드명(현재 앱) 모두 지원.
    """
    normalized: dict[str, Any] = {}

    # alias 우선 적용
    for alias, target in _FIELD_ALIASES.items():
        if alias in item and target not in normalized:
            normalized[target] = item[alias]

    # 이미 snake_case 필드명인 경우 직접 복사
    for field in (
        "bid_notice_no",
        "bid_notice_order",
        "notice_name",
        "demand_org",
        "notice_org",
        "posted_at",
        "business_type",
        "detail_url",
        "raw_detail_url_candidates",
    ):
        if field in item and field not in normalized:
            normalized[field] = item[field]

    # posted_at 후보 필드 (rgstDt가 없고 bidBeginDt도 없을 때)
    if "posted_at" not in normalized:
        for alt in ("ntceBeginDt", "opengDt", "drwtDt"):
            if alt in item:
                normalized["posted_at"] = item[alt]
                break

    # detail_url이 없으면 missing 표시
    normalized.setdefault("detail_url", None)
    normalized.setdefault("raw_detail_url_candidates", [])
    normalized["detail_url_missing"] = not bool(normalized.get("detail_url"))

    # 필수 필드 누락 확인
    missing = [f for f in _REQUIRED_ITEM_FIELDS if not normalized.get(f)]
    normalized["missing_required_fields"] = missing

    return normalized


def validate_g2b_notice_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """
    정규화된 candidate의 유효성을 검증하고 검증 결과를 반환한다.

    반환 필드:
      valid (bool), missing_required_fields, detail_url_verdict,
      safe_detail_url, blocked_detail_url, needs_verification_detail_url
    """
    missing = candidate.get("missing_required_fields", [])
    detail_url = candidate.get("detail_url") or ""
    url_verdict = _classify_url(detail_url) if detail_url else "missing"

    safe_detail = detail_url if url_verdict == "safe" else ""
    blocked_detail = detail_url if url_verdict == "blocked" else ""
    needs_v_detail = detail_url if url_verdict == "needs_verification" else ""

    # raw candidates 분류
    raw_candidates: list[str] = candidate.get("raw_detail_url_candidates", []) or []
    safe_extras, blocked_extras, needs_v_extras = [], [], []
    for u in raw_candidates:
        cls = _classify_url(u)
        if cls == "safe":
            safe_extras.append(u)
        elif cls == "blocked":
            blocked_extras.append(u)
        elif cls == "needs_verification":
            needs_v_extras.append(u)

    valid = not missing and not blocked_detail and url_verdict in ("safe", "missing", "external")

    return {
        "valid": valid,
        "missing_required_fields": missing,
        "detail_url_verdict": url_verdict,
        "safe_detail_url": safe_detail,
        "safe_extra_urls": safe_extras,
        "blocked_detail_url": blocked_detail,
        "blocked_extra_urls": blocked_extras,
        "needs_verification_detail_url": needs_v_detail,
        "needs_verification_extra_urls": needs_v_extras,
    }


def build_g2b_notice_candidates_from_existing_source(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    기존 OpenAPI 앱 payload를 현재 앱 candidate 목록으로 변환한다.

    입력 payload 필수 필드:
      source, items

    반환 필드:
      source, source_mode, api_key_used_by_current_app,
      api_key_value_exposed, db_read_direct, db_write,
      item_count, normalized_candidates,
      safe_detail_url_candidates, blocked_detail_url_candidates,
      needs_verification_candidates, detail_url_missing_count,
      missing_required_fields_count, verdict
    """
    result: dict[str, Any] = dict(_BRIDGE_POLICY_FIXED)
    result["source_mode"] = payload.get("source_mode", "exported_json")
    result["synthetic_sample"] = bool(payload.get("synthetic_sample", False))

    items: list[dict[str, Any]] = payload.get("items", []) or []
    result["item_count"] = len(items)

    normalized_candidates: list[dict[str, Any]] = []
    safe_detail_urls: list[str] = []
    blocked_detail_urls: list[str] = []
    needs_verification_urls: list[str] = []
    detail_url_missing_count = 0
    missing_required_fields_count = 0

    for item in items:
        norm = normalize_existing_g2b_openapi_item(item)
        validation = validate_g2b_notice_candidate(norm)
        enriched = {**norm, **validation}
        normalized_candidates.append(enriched)

        if enriched.get("safe_detail_url"):
            safe_detail_urls.append(enriched["safe_detail_url"])
        safe_detail_urls.extend(enriched.get("safe_extra_urls", []))

        if enriched.get("blocked_detail_url"):
            blocked_detail_urls.append(enriched["blocked_detail_url"])
        blocked_detail_urls.extend(enriched.get("blocked_extra_urls", []))

        if enriched.get("needs_verification_detail_url"):
            needs_verification_urls.append(enriched["needs_verification_detail_url"])
        needs_verification_urls.extend(enriched.get("needs_verification_extra_urls", []))

        if enriched.get("detail_url_missing"):
            detail_url_missing_count += 1
        if enriched.get("missing_required_fields"):
            missing_required_fields_count += 1

    result["normalized_candidates"] = normalized_candidates
    result["safe_detail_url_candidates"] = list(dict.fromkeys(safe_detail_urls))
    result["blocked_detail_url_candidates"] = list(dict.fromkeys(blocked_detail_urls))
    result["needs_verification_candidates"] = list(dict.fromkeys(needs_verification_urls))
    result["detail_url_missing_count"] = detail_url_missing_count
    result["missing_required_fields_count"] = missing_required_fields_count

    # verdict
    if missing_required_fields_count > 0:
        result["verdict"] = "WARN_MISSING_FIELDS"
    elif detail_url_missing_count == len(items) and len(items) > 0:
        result["verdict"] = "WARN_NO_DETAIL_URL"
    elif safe_detail_urls:
        result["verdict"] = "CANDIDATES_READY"
    else:
        result["verdict"] = "WARN_NO_SAFE_CANDIDATES"

    return result


def validate_existing_g2b_openapi_bridge_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    bridge payload의 정책 준수 여부를 검증한다.

    반환:
      valid (bool), violations (list), policy_fields
    """
    violations: list[str] = []

    # API key 노출 차단
    if payload.get("api_key_used_by_current_app") is True:
        violations.append("api_key_used_by_current_app must be False")
    if payload.get("api_key_value_exposed") is True:
        violations.append("api_key_value_exposed must be False")
    if payload.get("db_write") is True:
        violations.append("db_write must be False")
    if payload.get("db_read_direct") is True:
        violations.append("db_read_direct must be False")

    # source 확인
    if payload.get("source") not in (None, "existing_g2b_openapi_app"):
        violations.append(f"unexpected source: {payload.get('source')!r}")

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "policy_fields": {
            "api_key_used_by_current_app": False,
            "api_key_value_exposed": False,
            "db_read_direct": False,
            "db_write": False,
        },
    }


def classify_existing_source_bridge_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    build_g2b_notice_candidates_from_existing_source 결과를 분류하고
    content validator 입력 형태로 변환 가능한 payload를 반환한다.

    CONTENT_VALID_PASS는 content validator만 결정한다.
    이 함수는 bridge_verdict만 설정한다.
    """
    safe = result.get("safe_detail_url_candidates", [])
    blocked = result.get("blocked_detail_url_candidates", [])
    missing = result.get("detail_url_missing_count", 0)
    item_count = result.get("item_count", 0)

    if not item_count:
        bridge_verdict = "BRIDGE_EMPTY"
    elif safe:
        bridge_verdict = "BRIDGE_HAS_SAFE_CANDIDATES"
    elif blocked and not safe:
        bridge_verdict = "BRIDGE_ALL_BLOCKED"
    elif missing == item_count:
        bridge_verdict = "BRIDGE_ALL_URL_MISSING"
    else:
        bridge_verdict = "BRIDGE_PARTIAL"

    classified = dict(result)
    classified["bridge_verdict"] = bridge_verdict
    classified["content_valid_pass_set_by_bridge"] = False

    # content validator 입력 형태: safe URL 후보 목록
    classified["content_validator_input_candidates"] = [
        {
            "input_url": url,
            "final_url": url,
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "verdict": "",
            "mock_used": False,
            "local_agent_used": False,
            "server_browser_used": False,
            "links": [],
        }
        for url in safe
    ]

    return classified
