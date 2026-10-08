"""공통 헬퍼 — 경로 상수, 감사 로그, 타이밍."""
from __future__ import annotations

import time
from pathlib import Path

from ai_orchestrator.paths import repo_root
from ai_orchestrator.paths.runtime import data_dir, storage_dir

ROOT = repo_root()

_TOKEN_PATHS = [
    Path("/app/ai_orchestrator/storage/secrets/youtube_oauth_authorized_user.json"),
    storage_dir() / "secrets" / "youtube_oauth_authorized_user.json",
    # scripts.youtube.oauth 가 로컬(데스크톱) 인증 때 토큰을 쓰는 위치 — 읽는 쪽도 같이 본다
    data_dir() / "secrets" / "youtube_oauth_authorized_user.json",
]


def token_path() -> Path | None:
    for p in _TOKEN_PATHS:
        if p.exists():
            return p
    return None


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
