"""커뮤니티 자율 분석 스케줄 루프 (L8) — 서버 lifespan 에서 백그라운드 실행.

등록 사이트가 있으면 주기(기본 7일)마다 수집→분석→리포트 저장.
env:
  COMMUNITY_SCHEDULE_ENABLED       기본 "true"
  COMMUNITY_SCHEDULE_INTERVAL_SEC  기본 604800(7일)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INTERVAL = 604800  # 7일
_MAX_CHECK = 3600  # 점검 주기 상한(1시간)


def _enabled() -> bool:
    return os.environ.get("COMMUNITY_SCHEDULE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _interval_sec() -> int:
    try:
        v = int(os.environ.get("COMMUNITY_SCHEDULE_INTERVAL_SEC", str(_DEFAULT_INTERVAL)))
        return v if v >= 3600 else _DEFAULT_INTERVAL
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL


def _ensure_path() -> None:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


async def community_schedule_loop() -> None:
    """주기적으로 등록 사이트를 자율 분석. 사이트 없으면 건너뜀."""
    _ensure_path()
    # 기동 직후 한 박자 쉬고 시작(서버 안정화)
    await asyncio.sleep(60)
    while True:
        interval = _interval_sec()
        try:
            if _enabled():
                from scripts.community.registry import list_sites
                from scripts.community.scheduler import run_all_sites, seconds_since_last_run

                sites = await asyncio.to_thread(list_sites)
                since = await asyncio.to_thread(seconds_since_last_run)
                if sites and (since is None or since >= interval):
                    logger.info("[COMMUNITY-SCHED] 자율 분석 시작 (사이트 %d개)", len(sites))
                    rep = await asyncio.to_thread(run_all_sites, "scheduled")
                    logger.info("[COMMUNITY-SCHED] 완료 — %d/%d 성공", rep.get("ok_count", 0), rep.get("site_count", 0))
        except Exception:
            logger.exception("[COMMUNITY-SCHED] 루프 오류(무시)")
        await asyncio.sleep(min(interval, _MAX_CHECK))
