"""네이버 검색 collector 결과 저장 + 단순 Job 진입점.

- 비로그인 공개 수집 전용. 세션/재인증 흐름 없음.
- 동일 query 의 최신 실행 결과를 JSON 파일에 덮어쓴다 (1단계 구조 유지).
- 2단계: DB 적재(INSERT OR IGNORE) + 증분 수집 상태 파일 갱신 추가.
- 3단계: 실제 증분 수집 적용.
    * blog: state.last_collected_at 보다 과거 post_date 가 나오면 loop 종료.
    * shopping: 연속 duplicate 가 임계(DUPLICATE_STOP_THRESHOLD)에 도달하면 종료.
    * state 갱신은 실제 insert 가 1건 이상일 때만.
    * max_pages 기본 1 — 기존 호출자 동작 보존.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

from scripts.naver.shopping.naver_blog_collectors import collect_blog_search
from scripts.naver.shopping.naver_shopping_collectors import collect_shopping_search
from scripts.naver.shopping import naver_search_db as db_mod
from scripts.naver.shopping import naver_search_state as state_mod
from scripts.naver.shopping.naver_search_client import SOURCE_BLOG, SOURCE_SHOP, NaverSearchClient

logger = logging.getLogger(__name__)


# ── 3단계 증분 상수 ────────────────────────────────────────────
DEFAULT_MAX_PAGES = 1
# shopping 증분: 연속 N개 duplicate 가 나오면 이후 페이지도 대부분 중복이라 판단.
DUPLICATE_STOP_THRESHOLD = 20


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _repo_data_dir() -> Path:
    # ai_orchestrator/connectors/X.py → repo root /data
    return data_dir()


def default_blog_store_path() -> Path:
    override = os.environ.get("NAVER_BLOG_STORE_PATH", "").strip()
    return Path(override) if override else _repo_data_dir() / "naver_blog_search.json"


def default_shopping_store_path() -> Path:
    override = os.environ.get("NAVER_SHOPPING_STORE_PATH", "").strip()
    return Path(override) if override else _repo_data_dir() / "naver_shopping_search.json"


def save_search_record(path: Path, *, source: str, query: str, items: list) -> dict:
    """JSON 저장 (1단계 동작 유지). atomic replace.

    저장 구조: {source, query, collected_at, items}
    """
    record = {
        "source": source,
        "query": query,
        "collected_at": _utc_now_iso(),
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return record


# ── Job 결과 구조 ──────────────────────────────────────────────
@dataclass
class JobOutcome:
    status: str
    source: str
    query: str
    item_count: int
    saved_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    # 2단계: DB 적재 결과/상태.
    db_status: str = "disabled"  # "disabled" | "skipped_dry_run" | "ok" | "error"
    inserted_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    db_path: str | None = None
    db_error: str | None = None
    state_updated: bool = False
    # 3단계: 증분 관련.
    early_stop_reason: str | None = None  # None | "date_cutoff" | "duplicate_threshold"
    scanned_count: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "query": self.query,
            "item_count": self.item_count,
            "saved_path": self.saved_path,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "db_status": self.db_status,
            "inserted_count": self.inserted_count,
            "duplicate_count": self.duplicate_count,
            "skipped_count": self.skipped_count,
            "db_path": self.db_path,
            "db_error": self.db_error,
            "state_updated": self.state_updated,
            "early_stop_reason": self.early_stop_reason,
            "scanned_count": self.scanned_count,
        }


def _persist_if_data(
    *,
    status: str,
    source: str,
    query: str,
    items: list,
    store_path: Path,
) -> str | None:
    if status not in {"ok", "dry_run"} or not items:
        return None
    save_search_record(store_path, source=source, query=query, items=items)
    return str(store_path)


# ── DB 적재 (2단계 신규) ───────────────────────────────────────
def save_blog_items_to_db(
    query: str,
    items: list,
    *,
    db_path: Path | None = None,
) -> db_mod.InsertStats:
    """blog 결과를 DB 에 적재. 호출자가 enabled/live 상태를 선별한 뒤 부른다."""
    with db_mod.open_db(db_path) as conn:
        return db_mod.insert_blog_items(conn, query, items)


def save_shopping_items_to_db(
    query: str,
    items: list,
    *,
    db_path: Path | None = None,
) -> db_mod.InsertStats:
    """shopping 결과를 DB 에 적재."""
    with db_mod.open_db(db_path) as conn:
        return db_mod.insert_shopping_items(conn, query, items)


# ── 증분 수집 헬퍼 ─────────────────────────────────────────────
def _cutoff_date_from_state(
    source: str,
    query: str,
    state_path: Path | None,
) -> str | None:
    """state.last_collected_at (ISO8601 UTC) 에서 YYYY-MM-DD prefix 만 추출.

    값이 없거나 포맷이 짧으면 None.
    """
    last_ts = state_mod.get_last_collected_at(source, query, path=state_path)
    if not last_ts or len(last_ts) < 10:
        return None
    return last_ts[:10]


def _update_state_if_inserted(
    *,
    outcome: JobOutcome,
    source: str,
    query: str,
    state_path: Path | None,
) -> None:
    """실제 insert 가 있었을 때만 state 를 갱신한다."""
    if outcome.inserted_count <= 0:
        return
    try:
        state_mod.mark_query_collected(source, query, path=state_path)
        outcome.state_updated = True
    except Exception as e:  # noqa: BLE001 - 네이버 검색 수집 잡 -- 상태 파일 갱신/DB 저장·열기·닫기 실패를 로깅하고 outcome에 에러 상태만 기록, 수집 자체(읽기전용 검색 + 로컬 DB 적재)의 성공 여부 판정에는 영향 없음
        logger.warning("[NAVER-STATE-UPDATE-FAIL] type=%s", type(e).__name__)


def _blog_collect_with_cutoff(items: list, cutoff_date: str, accumulated: list) -> tuple[int, bool]:
    """cutoff 이전 post_date 가 나오면 중단. (scanned 증가분, cutoff_hit) 반환."""
    page_scanned = 0
    for item in items:
        page_scanned += 1
        pd = (item.get("post_date") or "").strip()
        if pd and pd < cutoff_date:
            return page_scanned, True
        accumulated.append(item)
    return page_scanned, False


def _blog_apply_db(
    outcome: JobOutcome,
    final_status: str,
    query: str,
    accumulated: list,
    db_path: Path | None,
    state_path: Path | None,
) -> None:
    """블로그 결과의 DB 적재 상태를 outcome 에 반영."""
    if final_status == "dry_run":
        outcome.db_status = "skipped_dry_run"
    elif final_status == "ok" and db_mod.is_db_enabled():
        try:
            stats = save_blog_items_to_db(query, accumulated, db_path=db_path)
        except Exception as e:
            logger.exception("[NAVER-BLOG-DB-ERR] type=%s", type(e).__name__)
            outcome.db_status = "error"
            outcome.db_error = type(e).__name__
        else:
            outcome.db_status = "ok"
            outcome.inserted_count = stats.inserted_count
            outcome.duplicate_count = stats.duplicate_count
            outcome.skipped_count = stats.skipped_count
            outcome.db_path = str(db_path or db_mod.default_db_path())
            _update_state_if_inserted(
                outcome=outcome,
                source=SOURCE_BLOG,
                query=query,
                state_path=state_path,
            )
    else:
        outcome.db_status = "disabled"


def _log_job_outcome(
    tag: str,
    outcome: JobOutcome,
    query: str,
    scanned: int,
    kept: int,
    saved: object,
) -> None:
    logger.info(
        tag + " status=%s query_len=%d scanned=%d kept=%d saved=%s "
        "db=%s inserted=%d dup=%d skipped=%d early_stop=%s",
        outcome.status,
        len(query or ""),
        scanned,
        kept,
        bool(saved),
        outcome.db_status,
        outcome.inserted_count,
        outcome.duplicate_count,
        outcome.skipped_count,
        outcome.early_stop_reason or "-",
    )


class _ShopRun:
    """쇼핑 Job 루프의 DB 적재 상태(연결·누적 통계·연속 중복 카운터)."""

    def __init__(self) -> None:
        self.agg = db_mod.InsertStats()
        self.consecutive = 0
        self.conn_cm: AbstractContextManager[Any] | None = None
        self.conn: Any = None  # conn_cm.__enter__() 결과(DB 연결) — 연결 열기 성공 후에만 사용
        self.db_error_name: str | None = None
        self.early_stop_reason: str | None = None


def _shop_insert_page(run: _ShopRun, query: str, items: list, db_path: Path | None, threshold: int | None) -> bool:
    """페이지를 DB 에 적재. 루프를 중단해야 하면 True."""
    if run.conn_cm is None:
        try:
            run.conn_cm = db_mod.open_db(db_path)
            run.conn = run.conn_cm.__enter__()
        except Exception as e:
            run.db_error_name = type(e).__name__
            logger.exception(
                "[NAVER-SHOPPING-DB-OPEN-ERR] type=%s",
                run.db_error_name,
            )
            return True
    try:
        page_stats = db_mod.insert_shopping_items(
            run.conn,
            query,
            items,
            stop_after_consecutive_duplicates=threshold,
            consecutive_duplicates_start=run.consecutive,
        )
    except Exception as e:
        run.db_error_name = type(e).__name__
        logger.exception(
            "[NAVER-SHOPPING-DB-ERR] type=%s",
            run.db_error_name,
        )
        return True
    run.agg.inserted_count += page_stats.inserted_count
    run.agg.duplicate_count += page_stats.duplicate_count
    run.agg.skipped_count += page_stats.skipped_count
    run.consecutive = page_stats.consecutive_duplicates
    if page_stats.stopped_early:
        run.early_stop_reason = "duplicate_threshold"
        return True
    return False


def _shop_apply_db(
    outcome: JobOutcome,
    run: _ShopRun,
    use_db: bool,
    query: str,
    db_path: Path | None,
    state_path: Path | None,
) -> None:
    """쇼핑 결과의 DB 적재 상태를 outcome 에 반영."""
    if outcome.status == "dry_run":
        outcome.db_status = "skipped_dry_run"
    elif outcome.status == "ok" and use_db:
        if run.db_error_name is not None:
            outcome.db_status = "error"
            outcome.db_error = run.db_error_name
        else:
            outcome.db_status = "ok"
            outcome.inserted_count = run.agg.inserted_count
            outcome.duplicate_count = run.agg.duplicate_count
            outcome.skipped_count = run.agg.skipped_count
            outcome.db_path = str(db_path or db_mod.default_db_path())
            _update_state_if_inserted(
                outcome=outcome,
                source=SOURCE_SHOP,
                query=query,
                state_path=state_path,
            )
    else:
        outcome.db_status = "disabled"


# ── Job 진입점 ──────────────────────────────────────────────────
def run_naver_blog_search_job(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    query: str,
    *,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    max_pages: int = DEFAULT_MAX_PAGES,
    client: NaverSearchClient | None = None,
    store_path: Path | None = None,
    db_path: Path | None = None,
    state_path: Path | None = None,
) -> JobOutcome:
    """블로그 증분 수집 Job.

    증분 전략:
        - state.last_collected_at (YYYY-MM-DD prefix) 보다 과거 post_date 가
          나오면 해당 페이지에서 루프 종료 (블로그는 최신순 정렬 가정).
        - dry_run / unconfigured 에서는 cutoff 적용하지 않는다.
    """
    path = store_path if store_path is not None else default_blog_store_path()
    pages_cap = max(1, int(max_pages))
    cutoff_date = _cutoff_date_from_state(SOURCE_BLOG, query, state_path)

    accumulated: list = []
    scanned = 0
    early_stop_reason: str | None = None
    final_status = "ok"
    final_err_code: str | None = None
    final_err_msg: str | None = None
    cur_start = int(start)

    for _ in range(pages_cap):
        result = collect_blog_search(
            query,
            display=display,
            start=cur_start,
            sort=sort,
            client=client,
        )
        final_status = result.status
        final_err_code = result.error_code
        final_err_msg = result.error_message

        if result.status not in {"ok", "dry_run"}:
            break

        # cutoff 는 live(ok) 에서만 의미. dry_run 은 mock 이라 필터 skip.
        if result.status == "ok" and cutoff_date:
            page_scanned, cutoff_hit = _blog_collect_with_cutoff(result.items, cutoff_date, accumulated)
            scanned += page_scanned
            if cutoff_hit:
                early_stop_reason = "date_cutoff"
                break
        else:
            scanned += len(result.items)
            accumulated.extend(result.items)

        # dry_run mock 은 페이지네이션 없음 — 1페이지만.
        if result.status == "dry_run":
            break
        # 마지막 페이지 도달
        if len(result.items) < display:
            break
        cur_start += display

    saved = _persist_if_data(
        status=final_status,
        source=SOURCE_BLOG,
        query=query,
        items=accumulated,
        store_path=path,
    )
    outcome = JobOutcome(
        status=final_status,
        source=SOURCE_BLOG,
        query=query,
        item_count=len(accumulated),
        saved_path=saved,
        error_code=final_err_code,
        error_message=final_err_msg,
        early_stop_reason=early_stop_reason,
        scanned_count=scanned,
    )

    # DB 적재 — status=="ok" + flag on 일 때만. dry_run/에러 skip.
    _blog_apply_db(outcome, final_status, query, accumulated, db_path, state_path)

    _log_job_outcome("[NAVER-BLOG-JOB]", outcome, query, scanned, len(accumulated), saved)
    return outcome


def run_naver_shopping_search_job(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    query: str,
    *,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    max_pages: int = DEFAULT_MAX_PAGES,
    duplicate_stop_threshold: int | None = DUPLICATE_STOP_THRESHOLD,
    client: NaverSearchClient | None = None,
    store_path: Path | None = None,
    db_path: Path | None = None,
    state_path: Path | None = None,
) -> JobOutcome:
    """쇼핑 증분 수집 Job.

    증분 전략:
        - shopping API 는 post_date 가 없어서 날짜 cutoff 적용 불가.
        - DB 연결이 enabled 인 경우, 각 페이지를 적재하며 연속 duplicate 를
          추적한다. threshold 도달 시 이후 페이지 호출을 중단.
    """
    path = store_path if store_path is not None else default_shopping_store_path()
    pages_cap = max(1, int(max_pages))
    use_db = db_mod.is_db_enabled()

    accumulated: list = []
    scanned = 0
    final_status = "ok"
    final_err_code: str | None = None
    final_err_msg: str | None = None
    cur_start = int(start)

    run = _ShopRun()

    try:
        for _ in range(pages_cap):
            result = collect_shopping_search(
                query,
                display=display,
                start=cur_start,
                sort=sort,
                client=client,
            )
            final_status = result.status
            final_err_code = result.error_code
            final_err_msg = result.error_message

            if result.status not in {"ok", "dry_run"}:
                break

            scanned += len(result.items)
            accumulated.extend(result.items)

            # live + flag on: 이 페이지를 바로 DB 에 적재해 duplicate 추이 관찰.
            if (
                result.status == "ok"
                and use_db
                and _shop_insert_page(run, query, result.items, db_path, duplicate_stop_threshold)
            ):
                break

            # dry_run mock 은 페이지네이션 없음 — 1페이지만.
            if result.status == "dry_run":
                break
            if len(result.items) < display:
                break
            cur_start += display
    finally:
        if run.conn_cm is not None:
            try:
                run.conn_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001 - 네이버 검색 수집 잡 -- 상태 파일 갱신/DB 저장·열기·닫기 실패를 로깅하고 outcome에 에러 상태만 기록, 수집 자체(읽기전용 검색 + 로컬 DB 적재)의 성공 여부 판정에는 영향 없음
                logger.warning("[NAVER-SHOPPING-DB-CLOSE-ERR]")

    saved = _persist_if_data(
        status=final_status,
        source=SOURCE_SHOP,
        query=query,
        items=accumulated,
        store_path=path,
    )
    outcome = JobOutcome(
        status=final_status,
        source=SOURCE_SHOP,
        query=query,
        item_count=len(accumulated),
        saved_path=saved,
        error_code=final_err_code,
        error_message=final_err_msg,
        early_stop_reason=run.early_stop_reason,
        scanned_count=scanned,
    )

    _shop_apply_db(outcome, run, use_db, query, db_path, state_path)

    _log_job_outcome("[NAVER-SHOPPING-JOB]", outcome, query, scanned, len(accumulated), saved)
    return outcome


__all__ = [
    "DEFAULT_MAX_PAGES",
    "DUPLICATE_STOP_THRESHOLD",
    "JobOutcome",
    "default_blog_store_path",
    "default_shopping_store_path",
    "run_naver_blog_search_job",
    "run_naver_shopping_search_job",
    "save_blog_items_to_db",
    "save_search_record",
    "save_shopping_items_to_db",
]
