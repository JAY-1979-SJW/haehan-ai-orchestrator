"""네이버 검색 잡 실행 기록 (JSONL append-only).

저장 경로: NAVER_SEARCH_RUN_LOG_PATH 또는 <repo>/data/naver_search_runs.jsonl
민감정보 기록 금지 — 허용 필드만 저장.
기록 실패가 본 수집을 깨지 않도록 write 예외는 모두 catch.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)

_SAFE_FIELDS = frozenset(
    {
        "job_type",
        "query",
        "started_at",
        "finished_at",
        "status",
        "scanned_count",
        "inserted_count",
        "duplicate_count",
        "skipped_count",
        "early_stop_reason",
        "db_status",
        "error_summary",
    }
)


def _repo_data_dir() -> Path:
    return data_dir()


def default_run_log_path() -> Path:
    override = os.environ.get("NAVER_SEARCH_RUN_LOG_PATH", "").strip()
    return Path(override) if override else _repo_data_dir() / "naver_search_runs.jsonl"


def append_run(record: dict, *, path: Path | None = None) -> None:
    """실행 기록을 JSONL 에 추가한다. 실패해도 호출자에게 예외를 전파하지 않는다."""
    p = path if path is not None else default_run_log_path()
    safe = {k: v for k, v in record.items() if k in _SAFE_FIELDS}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[NAVER-RUN-LOG-WRITE-FAIL] type=%s", type(e).__name__)


def load_recent_runs(n: int = 10, *, path: Path | None = None) -> list:
    """최근 N 건을 최신순으로 반환한다. 파일 없으면 빈 리스트."""
    p = path if path is not None else default_run_log_path()
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        records = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                with contextlib.suppress(json.JSONDecodeError):
                    records.append(json.loads(stripped))
        tail = records[-n:] if len(records) > n else records
        return list(reversed(tail))
    except Exception as e:  # noqa: BLE001
        logger.warning("[NAVER-RUN-LOG-READ-FAIL] type=%s", type(e).__name__)
        return []


__all__ = [
    "append_run",
    "default_run_log_path",
    "load_recent_runs",
]
