"""
Phase 1-L: Route Integration Skeleton Common
실제 route 등록 없음. decorator 없음. APIRouter 없음. feature flag 기본 OFF.
"""

from __future__ import annotations

PHASE = "PHASE_1L"
ROUTE_INTEGRATION_SKELETON_ONLY = True
ROUTE_REGISTERED = False
APP_INCLUDE_ROUTER_ALLOWED = False
ROUTE_DECORATOR_ALLOWED = False
FEATURE_FLAG_DEFAULT_ENABLED = False
FEATURE_FLAG_RUNTIME_HOOK_ALLOWED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ALLOWED = True
DB_WRITE_ALLOWED = False
HTTP_CALL_ALLOWED = False
SECRET_VALUE_ALLOWED = False
SERVER_APPLY_ALLOWED = False
NGINX_CHANGE_ALLOWED = False

_FORBIDDEN_ROUTE_CONTEXT_KEYS = frozenset({
    "request",
    "fastapi_request",
    "flask_request",
    "scope",
    "environ",
    "session",
    "db",
    "db_session",
    "user_context",
    "auth_context",
    "live_request",
    "app",
    "router",
})

_FORBIDDEN_SECRET_KEYS = frozenset({
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
})


class RouteIntegrationSkeletonError(Exception):
    pass


class RouteIntegrationDisabledError(RouteIntegrationSkeletonError):
    pass


class RouteIntegrationUnsafeExecutionError(RouteIntegrationSkeletonError):
    pass


def build_route_integration_disabled_result(
    route_id: str,
    adapter_id: str,
    reason: str,
) -> dict:
    return {
        "ok": False,
        "route_skeleton_id": route_id,
        "adapter_id": adapter_id,
        "route_registered": False,
        "feature_flag_enabled": False,
        "dry_run": False,
        "would_call_wrapper": False,
        "reason": reason,
    }


def assert_route_integration_flag_off(feature_flag_enabled: bool) -> None:
    if feature_flag_enabled:
        raise RouteIntegrationUnsafeExecutionError(
            "feature_flag_enabled=True is forbidden in Phase 1-L route integration skeleton. "
            "Route is not registered and live traffic is not allowed."
        )


def assert_route_integration_dry_run(
    dry_run: bool,
    fixture: dict | None,
) -> None:
    if dry_run and fixture is None:
        raise RouteIntegrationSkeletonError(
            "dry_run=True requires a fixture dict. Live payload is not allowed."
        )


def assert_no_live_route_context(payload: dict) -> None:
    if not payload:
        return
    for key in _FORBIDDEN_ROUTE_CONTEXT_KEYS:
        if key in payload:
            raise RouteIntegrationUnsafeExecutionError(
                f"Forbidden live route context key detected: '{key}'. "
                "Route integration skeleton does not accept live request objects."
            )
    for key in _FORBIDDEN_SECRET_KEYS:
        if key in payload:
            raise RouteIntegrationUnsafeExecutionError(
                f"Forbidden secret field detected: '{key}'. "
                "Secret values are not allowed in route integration skeleton."
            )
