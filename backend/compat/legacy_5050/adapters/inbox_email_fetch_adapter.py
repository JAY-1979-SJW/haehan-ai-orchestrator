"""Phase 1-F — INBOX_EMAIL_FETCH_ADAPTER skeleton.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01

이 파일은 PHASE_1F skeleton 전용입니다.
실제 email fetch / credential value 조회 / 외부 메일 서버 호출은 절대 금지입니다.
route 연결 없음. response normalization 구현 없음. Phase 1-G 이후에 구현 허용.

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask route decorator import 금지
    credential/env value 직접 조회 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

from typing import Any

from backend.compat.legacy_5050.adapters.common import (
    PHASE,
    AdapterSkeletonMetadata,
    SkeletonOnlyAdapterError,
)

# ── adapter 식별 상수 ──────────────────────────────────────────────────────────

ADAPTER_ID = "INBOX_EMAIL_FETCH_ADAPTER"
LEGACY_METHOD = "POST"
LEGACY_PATH_TEMPLATE = "/api/v1/inbox/email/fetch"
FASTAPI_METHOD = "POST"
FASTAPI_PATH_TEMPLATE = "/api/v1/inbox/email/fetch"
ADAPTER_TYPE = "CREDENTIAL_ENV_AND_RESPONSE_ADAPTER"
RISK_LEVEL = "MEDIUM"
REQUIRED_FEATURE_FLAG = "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED"
REQUIRED_SAFETY_GATE = "NO_LIVE_EMAIL_FETCH_IN_TESTS"


# ── metadata 함수 ─────────────────────────────────────────────────────────────

def get_adapter_metadata() -> AdapterSkeletonMetadata:
    return AdapterSkeletonMetadata(
        phase=PHASE,
        adapter_id=ADAPTER_ID,
        legacy_method=LEGACY_METHOD,
        legacy_path_template=LEGACY_PATH_TEMPLATE,
        fastapi_method=FASTAPI_METHOD,
        fastapi_path_template=FASTAPI_PATH_TEMPLATE,
        adapter_type=ADAPTER_TYPE,
        risk_level=RISK_LEVEL,
        required_feature_flag=REQUIRED_FEATURE_FLAG,
        required_safety_gate=REQUIRED_SAFETY_GATE,
    )


# ── adapt 함수 skeleton (호출 시 즉시 raise) ──────────────────────────────────

def adapt_inbox_email_fetch_request_response(*args: Any, **kwargs: Any) -> None:
    raise SkeletonOnlyAdapterError(
        adapter_id=ADAPTER_ID,
        message=(
            f"[PHASE_1F skeleton only] {ADAPTER_ID}: "
            "실제 구현 금지 — no live email fetch, "
            "no external mail server call, no credential value output. "
            "Phase 1-G 이후에 구현 허용."
        ),
    )
