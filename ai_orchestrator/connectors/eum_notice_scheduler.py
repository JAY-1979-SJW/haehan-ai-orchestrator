"""EUM(건설근로자공제회) 공지사항 감시 스케줄 루프 (L8) — 서버 lifespan 백그라운드 실행.

배경: 퇴직공제EDI·건설e음 시스템 장애/점검 시 사용자들이 "신고 기한 괜찮은지"
불안해하는 경우가 많다. 공지사항(WEBCEN010M00, 로그인 불필요)을 상시 감시해
장애·점검·기한연장 관련 신규 공지가 뜨면 즉시 감지한다. 자동 게시/알림 발송은
하지 않는다(외부 공개는 매번 사용자 확인 필요 — CLAUDE.md 정책). 감지 결과는
GET /api/v1/eum/notice-monitor 로 조회한다.

env:
  EUM_NOTICE_SCHEDULE_ENABLED       기본 "true"
  EUM_NOTICE_SCHEDULE_INTERVAL_SEC  기본 1800 (30분)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INTERVAL = 1800  # 30분


def _enabled() -> bool:
    return os.environ.get("EUM_NOTICE_SCHEDULE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _interval_sec() -> int:
    try:
        v = int(os.environ.get("EUM_NOTICE_SCHEDULE_INTERVAL_SEC", str(_DEFAULT_INTERVAL)))
        return v if v >= 300 else _DEFAULT_INTERVAL
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL


async def eum_notice_schedule_loop() -> None:
    """서버 lifespan에서 백그라운드로 실행되는 EUM 공지사항 감시 루프."""
    if not _enabled():
        logger.info("EUM 공지 스케줄 비활성화 (EUM_NOTICE_SCHEDULE_ENABLED)")
        return

    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    interval = _interval_sec()
    logger.info("EUM 공지 스케줄 시작 — 주기: %d초 (%.0f분)", interval, interval / 60)

    while True:
        try:
            from scripts.eum.notice_monitor import check_once_headless

            result = await asyncio.to_thread(check_once_headless)
            if result.get("alert_count"):
                logger.warning(
                    "EUM 공지 감시: 장애/점검성 신규 공지 %d건 감지",
                    result["alert_count"],
                )
            else:
                logger.info("EUM 공지 감시: 신규 %d건, 경보성 없음", result.get("new_count", 0))
        except Exception as e:
            logger.error("EUM 공지 감시 오류: %s", e)

        await asyncio.sleep(interval)
