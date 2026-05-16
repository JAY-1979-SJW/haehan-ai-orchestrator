"""Phase 1-F adapter skeleton 공통 정의.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1F_ADAPTER_SKELETON_ONLY_01

이 파일은 PHASE_1F skeleton 전용입니다.
실제 구현/route 연결/HTTP 호출/DB write/secret 조회는 절대 금지입니다.

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


# ── Skeleton-only 예외 ────────────────────────────────────────────────────────

class SkeletonOnlyAdapterError(NotImplementedError):
    """Phase 1-F skeleton adapter 호출 시 발생하는 예외.

    이 예외는 skeleton 단계에서 adapt 함수가 실제로 호출될 때 raise된다.
    실제 구현은 Phase 1-G 이후에 허용된다.
    live call, DB write, approve/reject 실행은 절대 금지이다.
    """

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
