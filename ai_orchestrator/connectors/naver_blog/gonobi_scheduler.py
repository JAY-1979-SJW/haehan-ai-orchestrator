"""gonobi 블로그 자동 수집 스케줄 루프 (L8) — 서버 lifespan 백그라운드 실행.

env:
  GONOBI_SCHEDULE_ENABLED       기본 "true"
  GONOBI_SCHEDULE_INTERVAL_SEC  기본 604800 (7일)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_INTERVAL = 604800  # 7일


def _enabled() -> bool:
    return os.environ.get("GONOBI_SCHEDULE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _interval_sec() -> int:
    try:
        v = int(os.environ.get("GONOBI_SCHEDULE_INTERVAL_SEC", str(_DEFAULT_INTERVAL)))
        return v if v >= 3600 else _DEFAULT_INTERVAL
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL


async def gonobi_schedule_loop() -> None:
    """서버 lifespan에서 백그라운드로 실행되는 주기적 수집 루프."""
    if not _enabled():
        logger.info("gonobi 스케줄 비활성화 (GONOBI_SCHEDULE_ENABLED)")
        return

    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    interval = _interval_sec()
    logger.info("gonobi 스케줄 시작 — 주기: %d초 (%.1f일)", interval, interval / 86400)

    while True:
        await asyncio.sleep(interval)
        try:
            logger.info("gonobi 정기 수집 시작")
            from scripts.naver.blog.gonobi.runner import run_scrape

            result = await asyncio.to_thread(run_scrape, delay=0.8)
            logger.info(
                "gonobi 정기 수집 완료: 총%d건 신규%d건 오류%d건",
                result.total,
                result.new,
                result.errors,
            )
        except Exception as e:  # noqa: BLE001 - 서버 lifespan 백그라운드 주기적 수집 루프 — 1회 수집 실패를 로그만 남기고 다음 주기에 재시도, 루프 자체가 죽지 않도록 하는 표준 스케줄러 패턴
            logger.error("gonobi 정기 수집 오류: %s", e)
