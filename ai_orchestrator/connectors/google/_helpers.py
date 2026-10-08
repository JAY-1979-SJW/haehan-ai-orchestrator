"""공통 헬퍼 — 경로 상수, 감사 로그, 타이밍."""
from __future__ import annotations

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def duration_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def audit(event: str, user: dict, *, status: str, note: str = "") -> None:
    from ai_orchestrator.audit.audit_logger import log_event
    log_event(
        event,
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision=status,
        note=note[:300],
    )
