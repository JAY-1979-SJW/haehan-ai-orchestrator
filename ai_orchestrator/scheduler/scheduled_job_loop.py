"""사용자 예약 작업 루프 — 서버 lifespan 에서 백그라운드로 돌며 실행 시각이 된 작업을 실행한다.

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
환경변수 SCHEDULED_JOBS_ENABLED(기본 true) 로 끌 수 있다. 틱 주기: SCHEDULED_JOBS_TICK_SEC(기본 30초).
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_TICK_SEC = 30


def _enabled() -> bool:
    return os.environ.get("SCHEDULED_JOBS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _tick_sec() -> int:
    try:
        return max(5, int(os.environ.get("SCHEDULED_JOBS_TICK_SEC", str(_DEFAULT_TICK_SEC))))
    except ValueError:
        return _DEFAULT_TICK_SEC


async def scheduled_job_loop() -> None:
    if not _enabled():
        logger.info("[SCHEDULED-JOBS] 비활성화 (SCHEDULED_JOBS_ENABLED)")
        return

    from ai_orchestrator.scheduler import scheduled_job_service as service

    try:
        stale = await asyncio.to_thread(service.recover)
        if stale:
            logger.warning("[SCHEDULED-JOBS] 중단된 회차 %d건을 실패로 정리", stale)
    except Exception:
        logger.exception("[SCHEDULED-JOBS] 시작 정리 오류(무시)")

    logger.info("[SCHEDULED-JOBS] 시작 — 틱 %d초", _tick_sec())
    while True:
        try:
            for run in await asyncio.to_thread(service.tick):
                logger.info("[SCHEDULED-JOBS] 회차 %s → %s", run["id"][:8], run["status"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[SCHEDULED-JOBS] 루프 오류(무시)")
        await asyncio.sleep(_tick_sec())
