"""발행 이력 캐시 — 중복 발행 방지. 순수 로직, 외부 미의존 (L1).

원본: scripts/naver/blog/marketing/topics.py 의 캐시 관리 부분만 추출.
원본 파일 전체를 가져오지 않은 이유: 모듈 최상단에서
`scripts.naver.automation.integration.ai_responder.AIResponder`(GPT 호출, 차단됨)를
import하기 때문에, 캐시 함수만 쓰려 해도 그 의존이 따라온다. 여기서는
캐시 관리(load/save/dedup)만 떼어냈다.
"""

from __future__ import annotations

import hashlib
import json
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from core.blog_accounts import get_account


def _cache_path(blog_id: str | None = None) -> _Path:
    return _Path(get_account(blog_id)["cache_file"])


def load_cache(blog_id: str | None = None) -> dict:
    """blog_id 생략 시 기본 계정 캐시. 계정별로 파일이 분리돼 있어 한 계정의
    발행 이력이 다른 계정의 중복 검사에 섞이지 않는다."""
    path = _cache_path(blog_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: S110, BLE001 - 캐시 파일 손상/형식불일치 시 빈 캐시로 폴백(치명적이지 않음)
            pass
    return {"topics": [], "posted": []}


def save_cache(cache: dict, blog_id: str | None = None) -> None:
    path = _cache_path(blog_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def topic_key(title: str) -> str:
    # 보안 해시 용도가 아니라 중복 검사용 짧은 지문(fingerprint)일 뿐이라 usedforsecurity=False 명시
    return hashlib.md5(title.strip().lower().encode(), usedforsecurity=False).hexdigest()[:12]


def is_duplicate(title: str, cache: dict) -> bool:
    key = topic_key(title)
    used_keys = {p.get("key") for p in cache.get("posted", [])}
    used_titles = {p.get("title", "").strip().lower() for p in cache.get("posted", [])}
    return key in used_keys or title.strip().lower() in used_titles
