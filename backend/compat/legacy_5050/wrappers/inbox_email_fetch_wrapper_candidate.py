"""Phase 1-H — INBOX_EMAIL_FETCH route wrapper candidate.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_01

이 파일은 route wrapper candidate 전용입니다.
실제 FastAPI/Flask route 연결 없음. feature flag 기본 OFF.
dry-run fixture 모드에서만 Phase 1-G pure function 호출 허용.

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask route decorator import 금지
    credential/env value 직접 조회 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

from typing import Any

from backend.compat.legacy_5050.adapters.inbox_email_fetch_adapter import (
    build_inbox_email_fetch_fastapi_request,
    normalize_inbox_email_fetch_response,
)
from backend.compat.legacy_5050.wrappers.common import (
    PHASE,
    RouteWrapperCandidateMetadata,
    RouteWrapperUnsafeExecutionError,
    assert_feature_flag_off,
    assert_no_route_context,
    build_disabled_wrapper_result,
)

# ── 상수 ──────────────────────────────────────────────────────────────────────

WRAPPER_ID = "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE"
ADAPTER_ID = "INBOX_EMAIL_FETCH_ADAPTER"
LEGACY_METHOD = "POST"
LEGACY_PATH_TEMPLATE = "/api/v1/inbox/email/fetch"
FASTAPI_METHOD = "POST"
FASTAPI_PATH_TEMPLATE = "/api/v1/inbox/email/fetch"
FEATURE_FLAG = "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED"
FEATURE_FLAG_DEFAULT = False
ROUTE_CONNECTED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ALLOWED = True
RISK_LEVEL = "MEDIUM"


# ── metadata ──────────────────────────────────────────────────────────────────

def get_inbox_email_fetch_wrapper_metadata() -> dict[str, Any]:
    meta = RouteWrapperCandidateMetadata(
        phase=PHASE,
        wrapper_id=WRAPPER_ID,
        adapter_id=ADAPTER_ID,
        legacy_method=LEGACY_METHOD,
        legacy_path_template=LEGACY_PATH_TEMPLATE,
        fastapi_method=FASTAPI_METHOD,
        fastapi_path_template=FASTAPI_PATH_TEMPLATE,
        feature_flag=FEATURE_FLAG,
        feature_flag_default=FEATURE_FLAG_DEFAULT,
        route_connected=ROUTE_CONNECTED,
        live_traffic_allowed=LIVE_TRAFFIC_ALLOWED,
        dry_run_allowed=DRY_RUN_ALLOWED,
        risk_level=RISK_LEVEL,
    )
    return meta.as_dict()


# ── wrapper candidate ─────────────────────────────────────────────────────────

def inbox_email_fetch_wrapper_candidate(
    legacy_request_fixture: dict[str, Any] | None = None,
    legacy_response_fixture: dict[str, Any] | None = None,
    *,
    feature_flag_enabled: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """inbox email fetch route wrapper candidate.

    feature_flag_enabled=True → RouteWrapperUnsafeExecutionError.
    dry_run=False → disabled result 반환.
    dry_run=True → fixture 기반 pure function 호출.
    실제 email fetch / HTTP / DB / secret 접근 없음.
    """
    assert_feature_flag_off(feature_flag_enabled)

    if not dry_run:
        result = build_disabled_wrapper_result(ADAPTER_ID)
        result["wrapper_id"] = WRAPPER_ID
        return result

    # dry-run fixture mode
    if legacy_request_fixture is None:
        raise RouteWrapperUnsafeExecutionError(
            "dry_run=True requires legacy_request_fixture — live data not allowed."
        )

    assert_no_route_context(legacy_request_fixture)

    # secret value 검사는 Phase 1-G pure function 내부에서 수행
    fastapi_request = build_inbox_email_fetch_fastapi_request(legacy_request_fixture)

    normalized_response: dict[str, Any] = {}
    if legacy_response_fixture is not None:
        assert_no_route_context(legacy_response_fixture)
        normalized_response = normalize_inbox_email_fetch_response(legacy_response_fixture)

    return {
        "ok": True,
        "wrapper_id": WRAPPER_ID,
        "adapter_id": ADAPTER_ID,
        "route_connected": False,
        "feature_flag_enabled": False,
        "dry_run": True,
        "would_call_adapter": True,
        "fastapi_request": fastapi_request,
        "normalized_response": normalized_response,
    }
