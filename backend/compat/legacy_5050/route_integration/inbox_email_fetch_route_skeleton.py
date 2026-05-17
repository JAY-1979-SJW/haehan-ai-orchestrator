"""
Phase 1-L: Inbox Email Fetch Route Integration Skeleton
실제 route 등록 없음. feature flag 기본 OFF. dry-run fixture only.
"""

from __future__ import annotations

from backend.compat.legacy_5050.route_integration.common import (
    DRY_RUN_ALLOWED,
    LIVE_TRAFFIC_ALLOWED,
    PHASE,
    ROUTE_REGISTERED,
    RouteIntegrationDisabledError,
    RouteIntegrationUnsafeExecutionError,
    assert_no_live_route_context,
    assert_route_integration_dry_run,
    assert_route_integration_flag_off,
    build_route_integration_disabled_result,
)
from backend.compat.legacy_5050.wrappers.inbox_email_fetch_wrapper_candidate import (
    inbox_email_fetch_wrapper_candidate,
)

ROUTE_SKELETON_ID = "INBOX_EMAIL_FETCH_ROUTE_INTEGRATION_SKELETON"
WRAPPER_ID = "INBOX_EMAIL_FETCH_ROUTE_WRAPPER_CANDIDATE"
ADAPTER_ID = "INBOX_EMAIL_FETCH_ADAPTER"
LEGACY_METHOD = "POST"
LEGACY_PATH_TEMPLATE = "/api/v1/inbox/email/fetch"
FASTAPI_METHOD = "POST"
FASTAPI_PATH_TEMPLATE = "/api/v1/inbox/email/fetch"
FEATURE_FLAG = "LEGACY_5050_INBOX_EMAIL_FETCH_ADAPTER_ENABLED"
FEATURE_FLAG_DEFAULT = False
ROUTE_REGISTERED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ALLOWED = True
RISK_LEVEL = "MEDIUM"


def get_inbox_email_fetch_route_skeleton_metadata() -> dict:
    return {
        "phase": PHASE,
        "route_skeleton_id": ROUTE_SKELETON_ID,
        "wrapper_id": WRAPPER_ID,
        "adapter_id": ADAPTER_ID,
        "legacy_method": LEGACY_METHOD,
        "legacy_path_template": LEGACY_PATH_TEMPLATE,
        "fastapi_method": FASTAPI_METHOD,
        "fastapi_path_template": FASTAPI_PATH_TEMPLATE,
        "feature_flag": FEATURE_FLAG,
        "feature_flag_default": FEATURE_FLAG_DEFAULT,
        "route_registered": ROUTE_REGISTERED,
        "live_traffic_allowed": LIVE_TRAFFIC_ALLOWED,
        "dry_run_allowed": DRY_RUN_ALLOWED,
        "risk_level": RISK_LEVEL,
    }


def inbox_email_fetch_route_integration_skeleton(
    route_payload_fixture: dict | None = None,
    *,
    feature_flag_enabled: bool = False,
    dry_run: bool = False,
) -> dict:
    assert_route_integration_flag_off(feature_flag_enabled)

    if not dry_run:
        return build_route_integration_disabled_result(
            route_id=ROUTE_SKELETON_ID,
            adapter_id=ADAPTER_ID,
            reason="feature flag off / route integration skeleton only",
        )

    assert_route_integration_dry_run(dry_run=dry_run, fixture=route_payload_fixture)
    assert_no_live_route_context(route_payload_fixture or {})

    wrapper_result = inbox_email_fetch_wrapper_candidate(
        legacy_request_fixture=route_payload_fixture,
        feature_flag_enabled=False,
        dry_run=True,
    )

    return {
        "ok": True,
        "route_skeleton_id": ROUTE_SKELETON_ID,
        "wrapper_id": WRAPPER_ID,
        "adapter_id": ADAPTER_ID,
        "route_registered": False,
        "feature_flag_enabled": False,
        "dry_run": True,
        "would_call_wrapper": True,
        "wrapper_result": wrapper_result,
    }
