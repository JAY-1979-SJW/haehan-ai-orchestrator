"""Phase 1-H wrapper candidate 공통 정의.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1H_ROUTE_WRAPPER_CANDIDATE_FEATURE_FLAG_OFF_01

이 파일은 route wrapper candidate 전용입니다.
실제 FastAPI/Flask route 연결 없음.
feature flag 기본 OFF. dry-run fixture 모드에서만 pure function 호출 허용.

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask route decorator import 금지
    os.environ 값 직접 출력 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Phase 1-H 전역 상수 ───────────────────────────────────────────────────────

PHASE = "PHASE_1H"
WRAPPER_CANDIDATE_ONLY = True
FEATURE_FLAG_DEFAULT_ENABLED = False
ROUTE_CONNECTED = False
LIVE_TRAFFIC_ALLOWED = False
DRY_RUN_ALLOWED = True
DB_WRITE_ALLOWED = False
HTTP_CALL_ALLOWED = False
SECRET_VALUE_ALLOWED = False
SERVER_APPLY_ALLOWED = False
NGINX_CHANGE_ALLOWED = False

# ── route context 금지 키 ─────────────────────────────────────────────────────

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
})


# ── 예외 ──────────────────────────────────────────────────────────────────────

class RouteWrapperCandidateError(Exception):
    """Phase 1-H wrapper candidate 기본 예외."""


class RouteWrapperDisabledError(RouteWrapperCandidateError):
    """feature flag OFF 또는 dry_run=False 상태에서 실행 시도 시 발생."""

    def __init__(self, wrapper_id: str = "UNKNOWN", reason: str = "") -> None:
        self.wrapper_id = wrapper_id
        super().__init__(
            f"[PHASE_1H wrapper disabled] {wrapper_id}: {reason or 'feature flag off / wrapper candidate only'}"
        )


class RouteWrapperUnsafeExecutionError(RouteWrapperCandidateError):
    """unsafe 실행 조건(feature flag ON, route context, secret 등) 감지 시 발생."""

    def __init__(self, reason: str = "unsafe execution detected") -> None:
        super().__init__(f"[PHASE_1H unsafe execution] {reason}")


# ── TypedDict 대신 dataclass 사용 ─────────────────────────────────────────────

@dataclass
class RouteWrapperCandidateMetadata:
    phase: str
    wrapper_id: str
    adapter_id: str
    legacy_method: str
    legacy_path_template: str
    fastapi_method: str
    fastapi_path_template: str
    feature_flag: str
    feature_flag_default: bool
    route_connected: bool
    live_traffic_allowed: bool
    dry_run_allowed: bool
    risk_level: str
    wrapper_candidate_only: bool = True
    db_write_allowed: bool = False
    http_call_allowed: bool = False
    secret_value_allowed: bool = False
    server_apply_allowed: bool = False
    nginx_change_allowed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "wrapper_id": self.wrapper_id,
            "adapter_id": self.adapter_id,
            "legacy_method": self.legacy_method,
            "legacy_path_template": self.legacy_path_template,
            "fastapi_method": self.fastapi_method,
            "fastapi_path_template": self.fastapi_path_template,
            "feature_flag": self.feature_flag,
            "feature_flag_default": self.feature_flag_default,
            "route_connected": self.route_connected,
            "live_traffic_allowed": self.live_traffic_allowed,
            "dry_run_allowed": self.dry_run_allowed,
            "risk_level": self.risk_level,
            "wrapper_candidate_only": self.wrapper_candidate_only,
            "db_write_allowed": self.db_write_allowed,
            "http_call_allowed": self.http_call_allowed,
            "secret_value_allowed": self.secret_value_allowed,
            "server_apply_allowed": self.server_apply_allowed,
            "nginx_change_allowed": self.nginx_change_allowed,
            **self.extra,
        }


@dataclass
class RouteWrapperCandidateResult:
    ok: bool
    wrapper_id: str
    adapter_id: str
    route_connected: bool
    feature_flag_enabled: bool
    dry_run: bool
    would_call_adapter: bool
    reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        base = {
            "ok": self.ok,
            "wrapper_id": self.wrapper_id,
            "adapter_id": self.adapter_id,
            "route_connected": self.route_connected,
            "feature_flag_enabled": self.feature_flag_enabled,
            "dry_run": self.dry_run,
            "would_call_adapter": self.would_call_adapter,
        }
        if self.reason:
            base["reason"] = self.reason
        base.update(self.extra)
        return base


# ── pure helper functions ─────────────────────────────────────────────────────

def build_disabled_wrapper_result(adapter_id: str, reason: str = "") -> dict[str, Any]:
    """feature flag OFF 또는 dry_run=False 상태의 disabled result를 반환."""
    return {
        "ok": False,
        "adapter_id": adapter_id,
        "route_connected": False,
        "feature_flag_enabled": False,
        "dry_run": False,
        "would_call_adapter": False,
        "reason": reason or "feature flag off / wrapper candidate only",
    }


def assert_feature_flag_off(feature_flag_enabled: bool) -> None:
    """feature_flag_enabled=True이면 RouteWrapperUnsafeExecutionError."""
    if feature_flag_enabled:
        raise RouteWrapperUnsafeExecutionError(
            "feature_flag_enabled=True is forbidden in Phase 1-H wrapper candidate. "
            "Route connection and live traffic are not allowed at this phase."
        )


def assert_dry_run_fixture_mode(dry_run: bool, fixture: dict[str, Any] | None) -> None:
    """dry_run=True이고 fixture가 있어야 pure function 호출 허용."""
    if dry_run and fixture is None:
        raise RouteWrapperUnsafeExecutionError(
            "dry_run=True requires a fixture dict — live data not allowed."
        )


def assert_no_route_context(payload: dict[str, Any]) -> None:
    """payload에 route context 키가 있으면 RouteWrapperUnsafeExecutionError."""
    for key in payload:
        if key.lower() in _FORBIDDEN_ROUTE_CONTEXT_KEYS:
            raise RouteWrapperUnsafeExecutionError(
                f"route context key detected in payload: {key!r}. "
                "Live route context is forbidden in Phase 1-H."
            )
