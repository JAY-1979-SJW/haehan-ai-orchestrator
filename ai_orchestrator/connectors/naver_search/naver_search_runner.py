"""네이버 검색 수집 주기 실행 (asyncio 백그라운드 태스크).

활성화 조건: NAVER_SEARCH_SCHEDULE_ENABLED=true
실행 간격:   NAVER_SEARCH_SCHEDULE_INTERVAL_SEC (기본 3600초)
쿼리 목록:   NAVER_BLOG_SEARCH_QUERIES / NAVER_SHOPPING_SEARCH_QUERIES (콤마 분리)

신규 스케줄러 프레임워크 없음 — asyncio.sleep 루프 + asyncio.to_thread 만 사용.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from scripts.naver.shopping.naver_search_jobs import run_naver_blog_search_job, run_naver_shopping_search_job
from scripts.naver.shopping.naver_search_run_log import append_run

logger = logging.getLogger(__name__)

ENV_SCHEDULE_ENABLED = "NAVER_SEARCH_SCHEDULE_ENABLED"
ENV_INTERVAL_SEC = "NAVER_SEARCH_SCHEDULE_INTERVAL_SEC"
ENV_BLOG_QUERIES = "NAVER_BLOG_SEARCH_QUERIES"
ENV_SHOP_QUERIES = "NAVER_SHOPPING_SEARCH_QUERIES"

_DEFAULT_INTERVAL_SEC = 3600
_MIN_INTERVAL_SEC = 60


def _is_enabled() -> bool:
    return os.environ.get(ENV_SCHEDULE_ENABLED, "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _interval_sec() -> int:
    try:
        v = int(os.environ.get(ENV_INTERVAL_SEC, str(_DEFAULT_INTERVAL_SEC)))
        return max(_MIN_INTERVAL_SEC, v)
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL_SEC


def _parse_queries(env_key: str) -> list:
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return []
    return [q.strip() for q in raw.split(",") if q.strip()]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _determine_status(outcome) -> str:
    if outcome.status in {"ok", "dry_run"}:
        return "warn" if outcome.db_status == "error" else "ok"
    return "fail"


def _run_blog_query(query: str, *, run_log_path: Path | None = None) -> None:
    started = _utc_now_iso()
    try:
        outcome = run_naver_blog_search_job(query)
    except Exception as e:
        logger.exception("[NAVER-SCHED-BLOG-ERR] query_len=%d type=%s", len(query), type(e).__name__)
        append_run(
            {
                "job_type": "blog",
                "query": query,
                "started_at": started,
                "finished_at": _utc_now_iso(),
                "status": "fail",
                "error_summary": type(e).__name__,
            },
            path=run_log_path,
        )
        return
    append_run(
        {
            "job_type": "blog",
            "query": query,
            "started_at": started,
            "finished_at": _utc_now_iso(),
            "status": _determine_status(outcome),
            "scanned_count": outcome.scanned_count,
            "inserted_count": outcome.inserted_count,
            "duplicate_count": outcome.duplicate_count,
            "skipped_count": outcome.skipped_count,
            "early_stop_reason": outcome.early_stop_reason,
            "db_status": outcome.db_status,
            "error_summary": outcome.error_code,
        },
        path=run_log_path,
    )


def _run_shop_query(query: str, *, run_log_path: Path | None = None) -> None:
    started = _utc_now_iso()
    try:
        outcome = run_naver_shopping_search_job(query)
    except Exception as e:
        logger.exception("[NAVER-SCHED-SHOP-ERR] query_len=%d type=%s", len(query), type(e).__name__)
        append_run(
            {
                "job_type": "shopping",
                "query": query,
                "started_at": started,
                "finished_at": _utc_now_iso(),
                "status": "fail",
                "error_summary": type(e).__name__,
            },
            path=run_log_path,
        )
        return
    append_run(
        {
            "job_type": "shopping",
            "query": query,
            "started_at": started,
            "finished_at": _utc_now_iso(),
            "status": _determine_status(outcome),
            "scanned_count": outcome.scanned_count,
            "inserted_count": outcome.inserted_count,
            "duplicate_count": outcome.duplicate_count,
            "skipped_count": outcome.skipped_count,
            "early_stop_reason": outcome.early_stop_reason,
            "db_status": outcome.db_status,
            "error_summary": outcome.error_code,
        },
        path=run_log_path,
    )


def run_scheduled_collection(*, run_log_path: Path | None = None) -> None:
    """한 사이클 실행. 동기 함수 — asyncio.to_thread() 로 호출된다.

    NAVER_SEARCH_SCHEDULE_ENABLED=false 이면 즉시 return.
    쿼리 목록이 비어 있으면 WARN 로그 후 skip 기록 없이 return.
    """
    if not _is_enabled():
        logger.debug("[NAVER-SCHED] NAVER_SEARCH_SCHEDULE_ENABLED=false — skip")
        return

    blog_queries = _parse_queries(ENV_BLOG_QUERIES)
    shop_queries = _parse_queries(ENV_SHOP_QUERIES)

    if not blog_queries:
        logger.warning("[NAVER-SCHED] 블로그 쿼리 없음 (NAVER_BLOG_SEARCH_QUERIES 미설정) — 블로그 skip")
    if not shop_queries:
        logger.warning("[NAVER-SCHED] 쇼핑 쿼리 없음 (NAVER_SHOPPING_SEARCH_QUERIES 미설정) — 쇼핑 skip")

    if not blog_queries and not shop_queries:
        logger.warning("[NAVER-SCHED] 블로그/쇼핑 쿼리 모두 비어 있음 — 사이클 건너뜀")
        append_run(
            {
                "job_type": "blog",
                "query": "",
                "started_at": _utc_now_iso(),
                "finished_at": _utc_now_iso(),
                "status": "skipped",
                "error_summary": "NO_QUERIES_CONFIGURED",
            },
            path=run_log_path,
        )
        return

    for query in blog_queries:
        logger.info("[NAVER-SCHED-BLOG] query_len=%d", len(query))
        _run_blog_query(query, run_log_path=run_log_path)

    for query in shop_queries:
        logger.info("[NAVER-SCHED-SHOP] query_len=%d", len(query))
        _run_shop_query(query, run_log_path=run_log_path)


async def schedule_loop() -> None:
    """FastAPI lifespan 에서 asyncio.create_task() 로 실행되는 루프."""
    logger.info("[NAVER-SCHED] 스케줄 루프 시작")
    while True:
        try:
            await asyncio.to_thread(run_scheduled_collection)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("[NAVER-SCHED-LOOP-ERR] type=%s", type(e).__name__)
        interval = _interval_sec()
        logger.debug("[NAVER-SCHED] 다음 실행까지 %ds 대기", interval)
        await asyncio.sleep(interval)


__all__ = [
    "ENV_BLOG_QUERIES",
    "ENV_SCHEDULE_ENABLED",
    "ENV_SHOP_QUERIES",
    "run_scheduled_collection",
    "schedule_loop",
]
