"""Phase 1-F / 1-G adapter 공통 정의.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01
ASSISTANT_BACKEND_5050_LEGACY_PHASE1G_ADAPTER_UNIT_IMPLEMENTATION_01

Phase 1-F: skeleton 전용 상수/예외/메타데이터.
Phase 1-G: pure unit helper/예외 추가 (route 연결/HTTP/DB/secret 접근 없음).

금지:
    HTTP client import 금지 (requests/httpx/urllib)
    DB client import 금지 (sqlite3/psycopg/sqlalchemy)
    FastAPI/Flask route decorator import 금지
    os.environ 값 직접 출력 금지
    subprocess/socket import 금지
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# ── Phase 1-F 전역 상수 ───────────────────────────────────────────────────────

PHASE = "PHASE_1F"
SKELETON_ONLY = True
IMPLEMENTATION_ALLOWED = False
LIVE_CALL_ALLOWED = False
SIDE_EFFECT_ALLOWED = False
DB_WRITE_ALLOWED = False
SECRET_VALUE_ALLOWED = False
ROUTE_HANDLER_CHANGE_ALLOWED = False
SERVER_APPLY_ALLOWED = False
NGINX_CHANGE_ALLOWED = False

# ── Phase 1-G 전역 상수 ───────────────────────────────────────────────────────

UNIT_PHASE = "PHASE_1G"
UNIT_IMPLEMENTATION_ALLOWED = True
ROUTE_CONNECTION_ALLOWED = False

# Phase 1-G에서도 동일하게 금지
_UNIT_LIVE_CALL_ALLOWED = False
_UNIT_SIDE_EFFECT_ALLOWED = False
_UNIT_DB_WRITE_ALLOWED = False
_UNIT_SECRET_VALUE_ALLOWED = False

# ── 금지 경로 목록 (STEP 2 helper 기준) ──────────────────────────────────────

_FORBIDDEN_PATH_FRAGMENTS = (
    "/execute",
    "/webhooks/",
    "kakaowork",
    "kakaotalk-channel",
    "/dashboard",
)

# ── Skeleton-only 예외 ────────────────────────────────────────────────────────

class SkeletonOnlyAdapterError(NotImplementedError):
    """Phase 1-F skeleton adapter 호출 시 발생하는 예외."""

    def __init__(
        self,
        adapter_id: str = "UNKNOWN",
        message: str | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        default_msg = (
            f"[PHASE_1F skeleton only] {adapter_id}: "
            "실제 구현 금지 — no live call, no DB write, "
            "approval gate not executed, no actual email fetch. "
            "Phase 1-G 이후에 구현 허용."
        )
        super().__init__(message or default_msg)


# ── Phase 1-G 예외 ────────────────────────────────────────────────────────────

class AdapterUnitMappingError(ValueError):
    """Phase 1-G pure unit function에서 매핑 불가 입력 시 발생하는 예외."""

    def __init__(self, reason: str = "invalid input") -> None:
        super().__init__(f"[PHASE_1G unit mapping error] {reason}")


# ── Phase 1-G pure helper functions ──────────────────────────────────────────

def ensure_no_double_slash(path: str) -> str:
    """경로에 double slash가 없으면 그대로 반환, 있으면 AdapterUnitMappingError."""
    if "//" in path:
        raise AdapterUnitMappingError(f"double slash detected in path: {path!r}")
    return path


def ensure_no_forbidden_path(path: str) -> str:
    """금지 경로 fragment가 포함되면 AdapterUnitMappingError."""
    for fragment in _FORBIDDEN_PATH_FRAGMENTS:
        if fragment in path:
            raise AdapterUnitMappingError(
                f"forbidden path fragment {fragment!r} detected in: {path!r}"
            )
    return path


_SECRET_FIELD_NAMES = frozenset({
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "credential_value",
    "smtp_password",
    "imap_password",
})


def ensure_no_secret_value_payload(payload: Mapping[str, Any]) -> None:
    """payload dict에 secret 의심 필드가 있으면 AdapterUnitMappingError."""
    for key in payload:
        if key.lower() in _SECRET_FIELD_NAMES:
            raise AdapterUnitMappingError(
                f"secret value field detected in payload: {key!r}"
            )


def normalize_status_code(value: Any) -> int:
    """status code를 int로 변환. 변환 불가 시 AdapterUnitMappingError."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AdapterUnitMappingError(
            f"cannot normalize status code: {value!r}"
        ) from exc


# ── Adapter skeleton metadata ─────────────────────────────────────────────────

@dataclass
class AdapterSkeletonMetadata:
    phase: str
    adapter_id: str
    legacy_method: str
    legacy_path_template: str
    fastapi_method: str
    fastapi_path_template: str
    adapter_type: str
    risk_level: str
    required_feature_flag: str
    required_safety_gate: str
    skeleton_only: bool = True
    implementation_allowed: bool = False
    live_call_allowed: bool = False
    side_effect_allowed: bool = False
    db_write_allowed: bool = False
    secret_value_allowed: bool = False
    route_handler_change_allowed: bool = False
    server_apply_allowed: bool = False
    nginx_change_allowed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase":                        self.phase,
            "adapter_id":                   self.adapter_id,
            "legacy_method":                self.legacy_method,
            "legacy_path_template":         self.legacy_path_template,
            "fastapi_method":               self.fastapi_method,
            "fastapi_path_template":        self.fastapi_path_template,
            "adapter_type":                 self.adapter_type,
            "risk_level":                   self.risk_level,
            "required_feature_flag":        self.required_feature_flag,
            "required_safety_gate":         self.required_safety_gate,
            "skeleton_only":                self.skeleton_only,
            "implementation_allowed":       self.implementation_allowed,
            "live_call_allowed":            self.live_call_allowed,
            "side_effect_allowed":          self.side_effect_allowed,
            "db_write_allowed":             self.db_write_allowed,
            "secret_value_allowed":         self.secret_value_allowed,
            "route_handler_change_allowed": self.route_handler_change_allowed,
            "server_apply_allowed":         self.server_apply_allowed,
            "nginx_change_allowed":         self.nginx_change_allowed,
            **self.extra,
        }
