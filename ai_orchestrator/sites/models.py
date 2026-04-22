"""사이트 자동화용 도메인 모델 (SiteTask / SiteExecutionResult / SiteHealthStatus).

기존 TaskRequest 와 분리된 namespace 로 둔다.
이번 단계는 구조 검증이 목적이므로 필드는 최소만 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal, Optional


ExecutionMode = Literal["dry_run", "check", "execute"]
HealthState = Literal["healthy", "degraded", "unavailable", "unconfigured"]
ResultStatus = Literal[
    "ok",
    "dry_run",
    "skipped",
    "unsupported_action",
    "not_implemented",
    "error",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SiteTask:
    """브라우저 작업 단위 요청.

    - target_site: 커넥터 registry 에 등록된 이름
    - action: 커넥터가 supports_action 으로 판정하는 식별자
    - execution_mode: 이번 단계는 dry_run/check 중심
    """
    task_id: str
    target_site: str
    action: str
    requested_by: str = "system"
    actor_role: str = ""
    params: dict = field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = False
    execution_mode: ExecutionMode = "dry_run"
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SiteExecutionResult:
    """dry_run / execute 결과. 민감 원문 필드는 담지 않는다."""
    task_id: str
    target_site: str
    action: str
    status: ResultStatus
    started_at: str = field(default_factory=_utc_now_iso)
    finished_at: str = field(default_factory=_utc_now_iso)
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    health_snapshot: Optional[dict] = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SiteHealthStatus:
    """단일 사이트 건강도 스냅샷."""
    site_name: str
    connector_name: str
    state: HealthState = "unconfigured"
    configured: bool = False
    credentials_present: bool = False
    session_state_present: bool = False
    browser_launch_ok: Optional[bool] = None
    login_check_status: str = "not_checked"
    last_checked_at: str = field(default_factory=_utc_now_iso)
    latency_ms: int = 0
    warning: str = ""
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = [
    "SiteTask",
    "SiteExecutionResult",
    "SiteHealthStatus",
    "ExecutionMode",
    "HealthState",
    "ResultStatus",
]
