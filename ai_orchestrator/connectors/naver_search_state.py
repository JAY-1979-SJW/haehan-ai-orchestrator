"""네이버 검색 증분 수집 기초 상태 파일.

이번 단계는 '상태 저장' 까지만. 실제 증분 최적화(start/postdate 기반 호출)는
다음 단계에서 이 파일을 읽어 결정하도록 분리한다.

구조 (data/naver_search_state.json):
    {
      "naver_blog":  {"파이썬": {"last_collected_at": "..."}},
      "naver_shop":  {"키보드": {"last_collected_at": "..."}}
    }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

logger = logging.getLogger(__name__)


SOURCE_BLOG = "naver_blog"
SOURCE_SHOP = "naver_shop"
_VALID_SOURCES = {SOURCE_BLOG, SOURCE_SHOP}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_state_path() -> Path:
    override = os.environ.get("NAVER_SEARCH_STATE_PATH", "").strip()
    if override:
        return Path(override)
    return data_dir() / "naver_search_state.json"


def _empty() -> dict:
    return {SOURCE_BLOG: {}, SOURCE_SHOP: {}}


def load_state(path: Path | None = None) -> dict:
    """상태 파일 로드. 없거나 파손 시 빈 레코드."""
    p = path or default_state_path()
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return _empty()
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[NAVER-STATE-READ-FAIL] err=%s", type(e).__name__)
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    # 스키마 안정화 — 누락 키는 빈 dict 로 채움
    out = _empty()
    for src in _VALID_SOURCES:
        section = data.get(src)
        out[src] = section if isinstance(section, dict) else {}
    return out


def save_state(path: Path | None, state: dict) -> None:
    p = path or default_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def mark_query_collected(
    source: str,
    query: str,
    *,
    collected_at: str | None = None,
    path: Path | None = None,
) -> dict:
    """query 에 대한 마지막 수집 시각을 기록하고 최신 상태 반환."""
    if source not in _VALID_SOURCES:
        raise ValueError(f"invalid source: {source!r}")
    if not query:
        raise ValueError("query 는 비어 있을 수 없다")
    ts = collected_at or _utc_now_iso()
    state = load_state(path)
    state[source][query] = {"last_collected_at": ts}
    save_state(path, state)
    return state


def get_last_collected_at(
    source: str,
    query: str,
    *,
    path: Path | None = None,
) -> str | None:
    if source not in _VALID_SOURCES or not query:
        return None
    state = load_state(path)
    entry = state.get(source, {}).get(query)
    if not isinstance(entry, dict):
        return None
    v = entry.get("last_collected_at")
    return v if isinstance(v, str) and v else None


__all__ = [
    "SOURCE_BLOG",
    "SOURCE_SHOP",
    "default_state_path",
    "get_last_collected_at",
    "load_state",
    "mark_query_collected",
    "save_state",
]
