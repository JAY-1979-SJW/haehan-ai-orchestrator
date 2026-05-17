"""Phase 1-H — TASK_APPROVE / TASK_REJECT route wrapper candidate.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_01

이 파일은 route wrapper candidate 전용입니다.
실제 FastAPI/Flask route 연결 없음. feature flag 기본 OFF.
dry-run fixture 모드에서만 Phase 1-G pure function 호출 허용.
approval_gate_executed는 항상 False.
/api/v1/tasks//approve 및 /api/v1/tasks//reject 절대 생성 금지.

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask route decorator import 금지
    approval gate 우회 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

from typing import Any

from backend.compat.legacy_5050.adapters.task_approval_adapter import (
    APPROVE_FASTAPI_PATH_TEMPLATE,
    APPROVE_LEGACY_PATH_TEMPLATE,
    REJECT_FASTAPI_PATH_TEMPLATE,
    REJECT_LEGACY_PATH_TEMPLATE,
    map_legacy_task_action_path_to_fastapi_path,
    normalize_task_approve_response,
    normalize_task_reject_response,
)
from backend.compat.legacy_5050.wrappers.common import (
    PHASE,
    RouteWrapperCandidateMetadata,
    RouteWrapperUnsafeExecutionError,
    assert_feature_flag_off,
    assert_no_route_context,
    build_disabled_wrapper_result,
)

# ── approve 상수 ──────────────────────────────────────────────────────────────

APPROVE_WRAPPER_ID = "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE"
APPROVE_ADAPTER_ID = "TASK_APPROVE_PATH_AUTH_ADAPTER"
APPROVE_LEGACY_METHOD = "POST"
APPROVE_FASTAPI_METHOD = "POST"
APPROVE_FEATURE_FLAG = "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED"
APPROVE_FEATURE_FLAG_DEFAULT = False
APPROVE_ROUTE_CONNECTED = False
APPROVE_LIVE_TRAFFIC_ALLOWED = False
APPROVE_DRY_RUN_ALLOWED = True
APPROVE_RISK_LEVEL = "HIGH"

# ── reject 상수 ───────────────────────────────────────────────────────────────

REJECT_WRAPPER_ID = "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE"
REJECT_ADAPTER_ID = "TASK_REJECT_PATH_AUTH_ADAPTER"
REJECT_LEGACY_METHOD = "POST"
REJECT_FASTAPI_METHOD = "POST"
REJECT_FEATURE_FLAG = "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED"
REJECT_FEATURE_FLAG_DEFAULT = False
REJECT_ROUTE_CONNECTED = False
REJECT_LIVE_TRAFFIC_ALLOWED = False
REJECT_DRY_RUN_ALLOWED = True
REJECT_RISK_LEVEL = "HIGH"


# ── metadata ──────────────────────────────────────────────────────────────────

def get_task_approve_wrapper_metadata() -> dict[str, Any]:
    meta = RouteWrapperCandidateMetadata(
        phase=PHASE,
        wrapper_id=APPROVE_WRAPPER_ID,
        adapter_id=APPROVE_ADAPTER_ID,
        legacy_method=APPROVE_LEGACY_METHOD,
        legacy_path_template=APPROVE_LEGACY_PATH_TEMPLATE,
        fastapi_method=APPROVE_FASTAPI_METHOD,
        fastapi_path_template=APPROVE_FASTAPI_PATH_TEMPLATE,
        feature_flag=APPROVE_FEATURE_FLAG,
        feature_flag_default=APPROVE_FEATURE_FLAG_DEFAULT,
        route_connected=APPROVE_ROUTE_CONNECTED,
        live_traffic_allowed=APPROVE_LIVE_TRAFFIC_ALLOWED,
        dry_run_allowed=APPROVE_DRY_RUN_ALLOWED,
        risk_level=APPROVE_RISK_LEVEL,
    )
    return meta.as_dict()


def get_task_reject_wrapper_metadata() -> dict[str, Any]:
    meta = RouteWrapperCandidateMetadata(
        phase=PHASE,
        wrapper_id=REJECT_WRAPPER_ID,
        adapter_id=REJECT_ADAPTER_ID,
        legacy_method=REJECT_LEGACY_METHOD,
        legacy_path_template=REJECT_LEGACY_PATH_TEMPLATE,
        fastapi_method=REJECT_FASTAPI_METHOD,
        fastapi_path_template=REJECT_FASTAPI_PATH_TEMPLATE,
        feature_flag=REJECT_FEATURE_FLAG,
        feature_flag_default=REJECT_FEATURE_FLAG_DEFAULT,
        route_connected=REJECT_ROUTE_CONNECTED,
        live_traffic_allowed=REJECT_LIVE_TRAFFIC_ALLOWED,
        dry_run_allowed=REJECT_DRY_RUN_ALLOWED,
        risk_level=REJECT_RISK_LEVEL,
    )
    return meta.as_dict()


# ── wrapper candidate ─────────────────────────────────────────────────────────

def task_approve_wrapper_candidate(
    task_id: str | None = None,
    response_fixture: dict[str, Any] | None = None,
    *,
    feature_flag_enabled: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """task approve route wrapper candidate.

    feature_flag_enabled=True → RouteWrapperUnsafeExecutionError.
    dry_run=False → disabled result 반환.
    dry_run=True → fixture 기반 pure function 호출.
    실제 approve / DB write / approval gate 실행 없음.
    approval_gate_executed는 항상 False.
    """
    assert_feature_flag_off(feature_flag_enabled)

    if not dry_run:
        result = build_disabled_wrapper_result(APPROVE_ADAPTER_ID)
        result["wrapper_id"] = APPROVE_WRAPPER_ID
        return result

    # dry-run fixture mode
    if not task_id or not task_id.strip():
        raise RouteWrapperUnsafeExecutionError(
            "task_id must not be empty in dry-run fixture mode."
        )

    path_mapping = map_legacy_task_action_path_to_fastapi_path(
        APPROVE_LEGACY_PATH_TEMPLATE,
        APPROVE_FASTAPI_PATH_TEMPLATE,
        task_id,
    )

    normalized_response: dict[str, Any] = {}
    if response_fixture is not None:
        assert_no_route_context(response_fixture)
        normalized_response = normalize_task_approve_response(response_fixture)
    else:
        normalized_response = normalize_task_approve_response(
            {"ok": True, "task_id": task_id}
        )

    # approval_gate_executed 강제 False 보장
    normalized_response["approval_gate_executed"] = False

    return {
        "ok": True,
        "wrapper_id": APPROVE_WRAPPER_ID,
        "adapter_id": APPROVE_ADAPTER_ID,
        "route_connected": False,
        "feature_flag_enabled": False,
        "dry_run": True,
        "would_call_adapter": True,
        "path_mapping": path_mapping,
        "normalized_response": normalized_response,
    }


def task_reject_wrapper_candidate(
    task_id: str | None = None,
    response_fixture: dict[str, Any] | None = None,
    *,
    feature_flag_enabled: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """task reject route wrapper candidate.

    feature_flag_enabled=True → RouteWrapperUnsafeExecutionError.
    dry_run=False → disabled result 반환.
    dry_run=True → fixture 기반 pure function 호출.
    실제 reject / DB write / approval gate 실행 없음.
    approval_gate_executed는 항상 False.
    """
    assert_feature_flag_off(feature_flag_enabled)

    if not dry_run:
        result = build_disabled_wrapper_result(REJECT_ADAPTER_ID)
        result["wrapper_id"] = REJECT_WRAPPER_ID
        return result

    # dry-run fixture mode
    if not task_id or not task_id.strip():
        raise RouteWrapperUnsafeExecutionError(
            "task_id must not be empty in dry-run fixture mode."
        )

    path_mapping = map_legacy_task_action_path_to_fastapi_path(
        REJECT_LEGACY_PATH_TEMPLATE,
        REJECT_FASTAPI_PATH_TEMPLATE,
        task_id,
    )

    normalized_response: dict[str, Any] = {}
    if response_fixture is not None:
        assert_no_route_context(response_fixture)
        normalized_response = normalize_task_reject_response(response_fixture)
    else:
        normalized_response = normalize_task_reject_response(
            {"ok": True, "task_id": task_id}
        )

    # approval_gate_executed 강제 False 보장
    normalized_response["approval_gate_executed"] = False

    return {
        "ok": True,
        "wrapper_id": REJECT_WRAPPER_ID,
        "adapter_id": REJECT_ADAPTER_ID,
        "route_connected": False,
        "feature_flag_enabled": False,
        "dry_run": True,
        "would_call_adapter": True,
        "path_mapping": path_mapping,
        "normalized_response": normalized_response,
    }
