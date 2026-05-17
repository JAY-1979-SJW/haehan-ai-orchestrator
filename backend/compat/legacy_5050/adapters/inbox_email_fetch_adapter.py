"""Phase 1-F / 1-G — INBOX_EMAIL_FETCH_ADAPTER.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01
ASSISTANT_BACKEND_5050_LEGACY_PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_01

Phase 1-F: skeleton 함수 (호출 시 SkeletonOnlyAdapterError raise).
Phase 1-G: pure unit function 추가 (route 연결/HTTP/DB/secret 접근 없음).

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
    AdapterUnitMappingError,
    SkeletonOnlyAdapterError,
    ensure_no_secret_value_payload,
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


# ── Phase 1-F adapt 함수 skeleton (호출 시 즉시 raise) ───────────────────────

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


# ── Phase 1-G pure unit functions ─────────────────────────────────────────────

_SAFE_REQUEST_FIELDS = frozenset({
    "limit",
    "labels",
    "include_attachments",
    "folder",
    "since",
    "until",
    "credential_ref",
    "credential_name",
    "page",
    "page_size",
})


def build_inbox_email_fetch_fastapi_request(legacy_request: dict[str, Any]) -> dict[str, Any]:
    """legacy request fixture를 FastAPI request shape로 변환.

    secret value 필드가 있으면 AdapterUnitMappingError를 raise한다.
    네트워크/DB/환경변수 접근 없음.
    """
    ensure_no_secret_value_payload(legacy_request)

    result: dict[str, Any] = {}
    for key, value in legacy_request.items():
        result[key] = value

    result.setdefault("adapter_id", ADAPTER_ID)
    result.setdefault("source", "legacy_5050")
    return result


def normalize_inbox_email_fetch_response(response: dict[str, Any]) -> dict[str, Any]:
    """response fixture를 표준 normalized shape로 변환.

    secret value 필드가 있으면 AdapterUnitMappingError를 raise한다.
    네트워크/DB/환경변수 접근 없음.
    """
    ensure_no_secret_value_payload(response)

    ok = bool(response.get("ok", response.get("success", True)))
    raw_fetched = response.get("fetched", response.get("count", len(response.get("items", []))))
    try:
        fetched = int(raw_fetched)
    except (TypeError, ValueError) as exc:
        raise AdapterUnitMappingError(
            f"cannot normalize fetched count: {raw_fetched!r}"
        ) from exc

    items = list(response.get("items", []))
    source = response.get("source", "legacy_5050")

    return {
        "ok": ok,
        "fetched": fetched,
        "items": items,
        "source": source,
        "adapter_id": ADAPTER_ID,
    }
