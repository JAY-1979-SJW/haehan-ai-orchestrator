"""개발자 등록 승인 게이트 감사 실행 로그.

안전 필드만 기록, 민감정보 원천 차단.

파일 위치:
  기본: <repo>/data/dev_reg_audit_runs.jsonl
  환경변수 DEV_REG_AUDIT_LOG_PATH 로 덮어쓰기 가능.

스키마 (안전 필드만):
  run_at             ISO UTC 타임스탬프
  result             PASS | WARN | FAIL
  pending_count      int
  expired_pending_count int
  expiry_soon_count  int
  recent_executed    int
  recent_rejected    int
  recent_failed      int
  warning_count      int
  warning_codes      list[str]  — 코드 prefix 만, 민감값 없음
  alert_sent         bool
  alert_type         HARD_FAIL | SOFT_WARN | NONE
  retry_candidate    bool
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)

_SAFE_FIELDS: frozenset[str] = frozenset(
    {
        "run_at",
        "result",
        "pending_count",
        "expired_pending_count",
        "expiry_soon_count",
        "recent_executed",
        "recent_rejected",
        "recent_failed",
        "warning_count",
        "warning_codes",
        "alert_sent",
        "alert_type",
        "retry_candidate",
    }
)


def default_audit_log_path() -> Path:
    env = os.environ.get("DEV_REG_AUDIT_LOG_PATH", "").strip()
    if env:
        return Path(env)
    return data_dir() / "dev_reg_audit_runs.jsonl"


def append_run(record: dict, *, path: Path | None = None) -> None:
    """안전 필드만 추출해 JSONL 에 추가한다. OSError 는 경고 로그만."""
    p = path if path is not None else default_audit_log_path()
    safe = {k: v for k, v in record.items() if k in _SAFE_FIELDS}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("dev_reg_audit_log 기록 실패: %s", e)


def load_recent_runs(n: int = 10, *, path: Path | None = None) -> list[dict]:
    """최신 N개 감사 실행 기록을 newest-first 로 반환한다."""
    p = path if path is not None else default_audit_log_path()
    if not p.exists():
        return []
    records: list[dict] = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return records[-n:][::-1]
