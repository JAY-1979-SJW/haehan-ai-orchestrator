"""Phase 1-F / 1-G — TASK_APPROVE / TASK_REJECT adapter.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01
ASSISTANT_BACKEND_5050_LEGACY_PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_01

Phase 1-F: skeleton 함수 (호출 시 SkeletonOnlyAdapterError raise).
Phase 1-G: pure unit function 추가 (route 연결/HTTP/DB/secret 접근 없음).
/api/v1/tasks//approve 및 /api/v1/tasks//reject 경로 절대 생성 금지.

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask route decorator import 금지
    approval gate 우회 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

from typing import Any

from backend.compat.legacy_5050.adapters.common import (
    PHASE,
    AdapterSkeletonMetadata,
    AdapterUnitMappingError,
    SkeletonOnlyAdapterError,
    ensure_no_double_slash,
)

# ── approve adapter 식별 상수 ─────────────────────────────────────────────────

APPROVE_ADAPTER_ID = "TASK_APPROVE_PATH_AUTH_ADAPTER"
APPROVE_LEGACY_METHOD = "POST"
APPROVE_LEGACY_PATH_TEMPLATE = "/api/v1/tasks/<id>/approve"
APPROVE_FASTAPI_METHOD = "POST"
APPROVE_FASTAPI_PATH_TEMPLATE = "/api/v1/tasks/{id}/approve"
APPROVE_ADAPTER_TYPE = "PATH_PARAM_AND_AUTH_POLICY_ADAPTER"
APPROVE_RISK_LEVEL = "HIGH"
APPROVE_REQUIRED_FEATURE_FLAG = "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED"
APPROVE_REQUIRED_SAFETY_GATE = "APPROVAL_GATE_REQUIRED_BUT_NOT_EXECUTED_IN_TESTS"

# ── reject adapter 식별 상수 ──────────────────────────────────────────────────

REJECT_ADAPTER_ID = "TASK_REJECT_PATH_AUTH_ADAPTER"
REJECT_LEGACY_METHOD = "POST"
REJECT_LEGACY_PATH_TEMPLATE = "/api/v1/tasks/<id>/reject"
REJECT_FASTAPI_METHOD = "POST"
REJECT_FASTAPI_PATH_TEMPLATE = "/api/v1/tasks/{id}/reject"
REJECT_ADAPTER_TYPE = "PATH_PARAM_AND_AUTH_POLICY_ADAPTER"
REJECT_RISK_LEVEL = "HIGH"
REJECT_REQUIRED_FEATURE_FLAG = "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED"
REJECT_REQUIRED_SAFETY_GATE = "APPROVAL_GATE_REQUIRED_BUT_NOT_EXECUTED_IN_TESTS"

_ALLOWED_ACTIONS = frozenset({"approve", "reject"})


# ── metadata 함수 ─────────────────────────────────────────────────────────────

def get_task_approve_adapter_metadata() -> AdapterSkeletonMetadata:
    return AdapterSkeletonMetadata(
        phase=PHASE,
        adapter_id=APPROVE_ADAPTER_ID,
        legacy_method=APPROVE_LEGACY_METHOD,
        legacy_path_template=APPROVE_LEGACY_PATH_TEMPLATE,
        fastapi_method=APPROVE_FASTAPI_METHOD,
        fastapi_path_template=APPROVE_FASTAPI_PATH_TEMPLATE,
        adapter_type=APPROVE_ADAPTER_TYPE,
        risk_level=APPROVE_RISK_LEVEL,
        required_feature_flag=APPROVE_REQUIRED_FEATURE_FLAG,
        required_safety_gate=APPROVE_REQUIRED_SAFETY_GATE,
    )


def get_task_reject_adapter_metadata() -> AdapterSkeletonMetadata:
    return AdapterSkeletonMetadata(
        phase=PHASE,
        adapter_id=REJECT_ADAPTER_ID,
        legacy_method=REJECT_LEGACY_METHOD,
        legacy_path_template=REJECT_LEGACY_PATH_TEMPLATE,
        fastapi_method=REJECT_FASTAPI_METHOD,
        fastapi_path_template=REJECT_FASTAPI_PATH_TEMPLATE,
        adapter_type=REJECT_ADAPTER_TYPE,
        risk_level=REJECT_RISK_LEVEL,
        required_feature_flag=REJECT_REQUIRED_FEATURE_FLAG,
        required_safety_gate=REJECT_REQUIRED_SAFETY_GATE,
    )


# ── Phase 1-F adapt 함수 skeleton (호출 시 즉시 raise) ───────────────────────

def adapt_task_approve_path_auth_response(*args: Any, **kwargs: Any) -> None:
    raise SkeletonOnlyAdapterError(
        adapter_id=APPROVE_ADAPTER_ID,
        message=(
            f"[PHASE_1F skeleton only] {APPROVE_ADAPTER_ID}: "
            "실제 구현 금지 — no actual approve execution, "
            "approval gate not executed, no DB write, no task state change. "
            "Phase 1-G 이후에 구현 허용."
        ),
    )


def adapt_task_reject_path_auth_response(*args: Any, **kwargs: Any) -> None:
    raise SkeletonOnlyAdapterError(
        adapter_id=REJECT_ADAPTER_ID,
        message=(
            f"[PHASE_1F skeleton only] {REJECT_ADAPTER_ID}: "
            "실제 구현 금지 — no actual reject execution, "
            "approval gate not executed, no DB write, no task state change. "
            "Phase 1-G 이후에 구현 허용."
        ),
    )


# ── Phase 1-G pure unit functions ─────────────────────────────────────────────

def map_legacy_task_action_path_to_fastapi_path(
    legacy_path_template: str,
    fastapi_path_template: str,
    task_id: str,
) -> dict[str, Any]:
    """legacy/fastapi path template에 task_id를 치환하여 sample path를 반환.

    네트워크/DB/환경변수 접근 없음. double slash 발생 시 AdapterUnitMappingError.
    """
    if not task_id or not task_id.strip():
        raise AdapterUnitMappingError("task_id must not be empty")

    # action 추출
    action = legacy_path_template.rstrip("/").split("/")[-1]
    if action not in _ALLOWED_ACTIONS:
        raise AdapterUnitMappingError(
            f"action must be one of {sorted(_ALLOWED_ACTIONS)}, got: {action!r}"
        )

    adapter_id = (
        APPROVE_ADAPTER_ID if action == "approve" else REJECT_ADAPTER_ID
    )

    legacy_path = legacy_path_template.replace("<id>", task_id)
    fastapi_path = fastapi_path_template.replace("{id}", task_id)

    ensure_no_double_slash(legacy_path)
    ensure_no_double_slash(fastapi_path)

    return {
        "legacy_path": legacy_path,
        "fastapi_path": fastapi_path,
        "task_id": task_id,
        "action": action,
        "adapter_id": adapter_id,
    }


def normalize_task_approve_response(response: dict[str, Any]) -> dict[str, Any]:
    """approve response fixture를 표준 normalized shape로 변환.

    실제 approve 호출 없음. DB write 없음. approval_gate_executed는 항상 False.
    """
    ok = bool(response.get("ok", response.get("success", True)))
    task_id = str(response.get("task_id", ""))

    return {
        "ok": ok,
        "status": "approved",
        "task_id": task_id,
        "adapter_id": APPROVE_ADAPTER_ID,
        "approval_gate_required": True,
        "approval_gate_executed": False,
    }


def normalize_task_reject_response(response: dict[str, Any]) -> dict[str, Any]:
    """reject response fixture를 표준 normalized shape로 변환.

    실제 reject 호출 없음. DB write 없음. approval_gate_executed는 항상 False.
    """
    ok = bool(response.get("ok", response.get("success", True)))
    task_id = str(response.get("task_id", ""))

    return {
        "ok": ok,
        "status": "rejected",
        "task_id": task_id,
        "adapter_id": REJECT_ADAPTER_ID,
        "approval_gate_required": True,
        "approval_gate_executed": False,
    }
