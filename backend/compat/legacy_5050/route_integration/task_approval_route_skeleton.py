"""
Phase 1-L: Task Approval Route Integration Skeleton (approve + reject)
실제 route 등록 없음. feature flag 기본 OFF. dry-run fixture only.
approval_gate_executed 항상 False.
"""

from __future__ import annotations

from backend.compat.legacy_5050.route_integration.common import (
    DRY_RUN_ALLOWED,
    LIVE_TRAFFIC_ALLOWED,
    PHASE,
    ROUTE_REGISTERED,
    RouteIntegrationSkeletonError,
    RouteIntegrationUnsafeExecutionError,
    assert_no_live_route_context,
    assert_route_integration_dry_run,
    assert_route_integration_flag_off,
    build_route_integration_disabled_result,
)
from backend.compat.legacy_5050.wrappers.task_approval_wrapper_candidate import (
    task_approve_wrapper_candidate,
    task_reject_wrapper_candidate,
)

# ── Approve ──────────────────────────────────────────────────────────────────

APPROVE_ROUTE_SKELETON_ID = "TASK_APPROVE_ROUTE_INTEGRATION_SKELETON"
APPROVE_WRAPPER_ID = "TASK_APPROVE_ROUTE_WRAPPER_CANDIDATE"
APPROVE_ADAPTER_ID = "TASK_APPROVE_PATH_AUTH_ADAPTER"
APPROVE_LEGACY_METHOD = "POST"
APPROVE_LEGACY_PATH_TEMPLATE = "/api/v1/tasks/<id>/approve"
APPROVE_FASTAPI_METHOD = "POST"
APPROVE_FASTAPI_PATH_TEMPLATE = "/api/v1/tasks/{id}/approve"
APPROVE_FEATURE_FLAG = "LEGACY_5050_TASK_APPROVE_ADAPTER_ENABLED"
APPROVE_FEATURE_FLAG_DEFAULT = False
APPROVE_ROUTE_REGISTERED = False
APPROVE_LIVE_TRAFFIC_ALLOWED = False
APPROVE_DRY_RUN_ALLOWED = True
APPROVE_RISK_LEVEL = "HIGH"

# ── Reject ────────────────────────────────────────────────────────────────────

REJECT_ROUTE_SKELETON_ID = "TASK_REJECT_ROUTE_INTEGRATION_SKELETON"
REJECT_WRAPPER_ID = "TASK_REJECT_ROUTE_WRAPPER_CANDIDATE"
REJECT_ADAPTER_ID = "TASK_REJECT_PATH_AUTH_ADAPTER"
REJECT_LEGACY_METHOD = "POST"
REJECT_LEGACY_PATH_TEMPLATE = "/api/v1/tasks/<id>/reject"
REJECT_FASTAPI_METHOD = "POST"
REJECT_FASTAPI_PATH_TEMPLATE = "/api/v1/tasks/{id}/reject"
REJECT_FEATURE_FLAG = "LEGACY_5050_TASK_REJECT_ADAPTER_ENABLED"
REJECT_FEATURE_FLAG_DEFAULT = False
REJECT_ROUTE_REGISTERED = False
REJECT_LIVE_TRAFFIC_ALLOWED = False
REJECT_DRY_RUN_ALLOWED = True
REJECT_RISK_LEVEL = "HIGH"


# ── Metadata ──────────────────────────────────────────────────────────────────

def get_task_approve_route_skeleton_metadata() -> dict:
    return {
        "phase": PHASE,
        "route_skeleton_id": APPROVE_ROUTE_SKELETON_ID,
        "wrapper_id": APPROVE_WRAPPER_ID,
        "adapter_id": APPROVE_ADAPTER_ID,
        "legacy_method": APPROVE_LEGACY_METHOD,
        "legacy_path_template": APPROVE_LEGACY_PATH_TEMPLATE,
        "fastapi_method": APPROVE_FASTAPI_METHOD,
        "fastapi_path_template": APPROVE_FASTAPI_PATH_TEMPLATE,
        "feature_flag": APPROVE_FEATURE_FLAG,
        "feature_flag_default": APPROVE_FEATURE_FLAG_DEFAULT,
        "route_registered": APPROVE_ROUTE_REGISTERED,
        "live_traffic_allowed": APPROVE_LIVE_TRAFFIC_ALLOWED,
        "dry_run_allowed": APPROVE_DRY_RUN_ALLOWED,
        "risk_level": APPROVE_RISK_LEVEL,
    }


def get_task_reject_route_skeleton_metadata() -> dict:
    return {
        "phase": PHASE,
        "route_skeleton_id": REJECT_ROUTE_SKELETON_ID,
        "wrapper_id": REJECT_WRAPPER_ID,
        "adapter_id": REJECT_ADAPTER_ID,
        "legacy_method": REJECT_LEGACY_METHOD,
        "legacy_path_template": REJECT_LEGACY_PATH_TEMPLATE,
        "fastapi_method": REJECT_FASTAPI_METHOD,
        "fastapi_path_template": REJECT_FASTAPI_PATH_TEMPLATE,
        "feature_flag": REJECT_FEATURE_FLAG,
        "feature_flag_default": REJECT_FEATURE_FLAG_DEFAULT,
        "route_registered": REJECT_ROUTE_REGISTERED,
        "live_traffic_allowed": REJECT_LIVE_TRAFFIC_ALLOWED,
        "dry_run_allowed": REJECT_DRY_RUN_ALLOWED,
        "risk_level": REJECT_RISK_LEVEL,
    }


# ── Skeleton functions ────────────────────────────────────────────────────────

def task_approve_route_integration_skeleton(
    task_id: str | None = None,
    response_fixture: dict | None = None,
    *,
    feature_flag_enabled: bool = False,
    dry_run: bool = False,
) -> dict:
    assert_route_integration_flag_off(feature_flag_enabled)

    if not dry_run:
        return build_route_integration_disabled_result(
            route_id=APPROVE_ROUTE_SKELETON_ID,
            adapter_id=APPROVE_ADAPTER_ID,
            reason="feature flag off / route integration skeleton only",
        )

    if not task_id:
        raise RouteIntegrationSkeletonError(
            "task_id is required for task_approve_route_integration_skeleton in dry-run mode."
        )

    assert_route_integration_dry_run(dry_run=dry_run, fixture=response_fixture)

    wrapper_result = task_approve_wrapper_candidate(
        task_id=task_id,
        response_fixture=response_fixture,
        feature_flag_enabled=False,
        dry_run=True,
    )

    # approval_gate_executed 강제 False 보장
    if isinstance(wrapper_result, dict):
        nr = wrapper_result.get("normalized_response", {})
        if isinstance(nr, dict):
            nr["approval_gate_executed"] = False

    return {
        "ok": True,
        "route_skeleton_id": APPROVE_ROUTE_SKELETON_ID,
        "wrapper_id": APPROVE_WRAPPER_ID,
        "adapter_id": APPROVE_ADAPTER_ID,
        "route_registered": False,
        "feature_flag_enabled": False,
        "dry_run": True,
        "would_call_wrapper": True,
        "wrapper_result": wrapper_result,
    }


def task_reject_route_integration_skeleton(
    task_id: str | None = None,
    response_fixture: dict | None = None,
    *,
    feature_flag_enabled: bool = False,
    dry_run: bool = False,
) -> dict:
    assert_route_integration_flag_off(feature_flag_enabled)

    if not dry_run:
        return build_route_integration_disabled_result(
            route_id=REJECT_ROUTE_SKELETON_ID,
            adapter_id=REJECT_ADAPTER_ID,
            reason="feature flag off / route integration skeleton only",
        )

    if not task_id:
        raise RouteIntegrationSkeletonError(
            "task_id is required for task_reject_route_integration_skeleton in dry-run mode."
        )

    assert_route_integration_dry_run(dry_run=dry_run, fixture=response_fixture)

    wrapper_result = task_reject_wrapper_candidate(
        task_id=task_id,
        response_fixture=response_fixture,
        feature_flag_enabled=False,
        dry_run=True,
    )

    # approval_gate_executed 강제 False 보장
    if isinstance(wrapper_result, dict):
        nr = wrapper_result.get("normalized_response", {})
        if isinstance(nr, dict):
            nr["approval_gate_executed"] = False

    return {
        "ok": True,
        "route_skeleton_id": REJECT_ROUTE_SKELETON_ID,
        "wrapper_id": REJECT_WRAPPER_ID,
        "adapter_id": REJECT_ADAPTER_ID,
        "route_registered": False,
        "feature_flag_enabled": False,
        "dry_run": True,
        "would_call_wrapper": True,
        "wrapper_result": wrapper_result,
    }
