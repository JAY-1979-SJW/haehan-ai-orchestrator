"""YouTube 검색 결과 SQLite 캐시 - scripts/youtube 와 scripts/google/youtube 두 도메인이 공유.

정리 배경(docs/defect_index.json #15): 두 도메인이 각자 동일한 search_cache 테이블을
동일한 DB 파일(data/youtube_search_cache.db)에 정의하고 있었다(복붙 중복). YouTube Search
Queries 쿼터(100회/일, 일반 쿼터 10,000회/일보다 훨씬 낮음)를 같은 쿼리 반복 검색으로 쉽게
소진하는 걸 막기 위해 두 경로가 같은 캐시 DB를 공유해야 하는데, CLAUDE.md의
"서로 다른 업무 도메인 간 직접 import 금지" 규칙상 두 도메인이 서로를 import할 수 없어
각자 사본을 뒀던 것 - 그 사본을 이 공용 모듈(scripts/common, 두 도메인 모두 하위 의존 가능한
위치) 하나로 합친다. 동작(DB 경로/스키마/TTL)은 기존과 완전히 동일하게 유지.

사용:
    from scripts.common.youtube_search_cache import cache_key, cache_get, cache_set
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

# 프로젝트 루트(이 파일 기준 두 단계 위) - 기존 두 사본과 동일한 경로를 그대로 유지.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH_CACHE_DB = data_dir() / "youtube_search_cache.db"
CACHE_TTL_SECONDS = 86_400  # 24시간
_PRUNE_AGE_SECONDS = 259_200  # 72시간


def cache_key(query: str, max_results: int, captions_only: bool = False) -> str:
    raw = f"{query.strip().lower()}|{max_results}|{captions_only}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> dict[str, Any] | None:
    try:
        SEARCH_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(SEARCH_CACHE_DB))
        row = con.execute("SELECT payload, cached_at FROM search_cache WHERE cache_key=?", (key,)).fetchone()
        con.close()
        if row and (time.time() - row[1]) < CACHE_TTL_SECONDS:
            return json.loads(row[0])
    except Exception:  # noqa: BLE001 - SQLite 캐시 조회/저장 실패는 캐시미스로 간주해 무시 - 캐시는 성능최적화 부가기능일 뿐 핵심 검색 로직에 영향 없음
        pass
    return None


def cache_set(key: str, payload: dict[str, Any]) -> None:
    try:
        SEARCH_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(SEARCH_CACHE_DB))
        con.execute(
            "CREATE TABLE IF NOT EXISTS search_cache (cache_key TEXT PRIMARY KEY, payload TEXT, cached_at REAL)"
        )
        con.execute(
            "INSERT OR REPLACE INTO search_cache VALUES (?,?,?)",
            (key, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        con.execute("DELETE FROM search_cache WHERE cached_at < ?", (time.time() - _PRUNE_AGE_SECONDS,))
        con.commit()
        con.close()
    except Exception:  # noqa: BLE001 - SQLite 캐시 조회/저장 실패는 캐시미스로 간주해 무시 - 캐시는 성능최적화 부가기능일 뿐 핵심 검색 로직에 영향 없음
        pass
