"""블로그 이미지(Unsplash) 해석 서비스 — 검색·로컬 캐시 폴백·다운로드.

원래 `ai_orchestrator/connectors/naver_blog/naver_blog_router.py`(L8 라우터) 안에 있던 헬퍼를 옮겼다. CLI 스크립트(L6)가 라우터를 import 하지 않고
이 모듈을 쓰도록 하기 위해서다(층간 위반 정리, 2026-10-01). 블로그 전용이라 `scripts/naver/blog/` 에 둔다(services 에 두면 scripts 와 새 모듈 순환이 생김).
라우터는 같은 이름으로 다시 내보내므로 기존 import 는 그대로 동작한다.

- Unsplash 공개 검색 API(AI 아님, 허용된 외부 API)와 로컬 캐시(data/unsplash_images.json)만 사용한다. 유료 AI 호출 없음.
- 다운로드한 이미지는 data/blog_uploads 에 저장한다.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.realtime_audit import emit_event

_log = logging.getLogger(__name__)

UPLOADS_DIR = data_dir() / "blog_uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_UNSPLASH_CACHE = data_dir() / "unsplash_images.json"
_UNSPLASH_API = "https://api.unsplash.com"


def _unsplash_key() -> str:
    return os.environ.get("UNSPLASH_ACCESS_KEY", "")


_TOPIC_KEYWORD_MAP: dict[str, str] = {
    "조명": "interior lighting",
    "led": "led light",
    "무드등": "mood lamp",
    "인테리어": "interior design",
    "가구": "furniture",
    "주방": "kitchen",
    "거실": "living room",
    "침실": "bedroom",
    "office": "office interior",
    "사무실": "office interior",
    "카페": "cafe interior",
    "매장": "retail store",
    "공장": "factory",
    "건축": "architecture",
    "정원": "garden",
}


def _unsplash_english_query(topic: str) -> str:
    """한국어 주제 → Unsplash 검색용 영어 키워드(3단어 이내) 변환.

    2026-09-24: 유료 AI(GPT) 호출 제거 — 고정 키워드 사전 매칭만 사용한다.
    """
    low = (topic or "").lower()
    for kw, en in _TOPIC_KEYWORD_MAP.items():
        if kw in low:
            return en
    return "interior design"


def _unsplash_live_search(topic: str, count: int) -> list[str]:
    """Unsplash 공개 검색 API(AI 아님, 허용된 외부 API)로 실시간 이미지 검색·다운로드.

    쿼리: 영어 3단어 이내 / orientation=landscape (해한 AI 홈페이지 프로젝트 검증된 방식과 동일).
    """
    key = _unsplash_key()
    if not key:
        return []

    import hashlib
    import time

    import requests as _req

    query = _unsplash_english_query(topic)
    resp = _req.get(
        f"{_UNSPLASH_API}/search/photos",
        params={"query": query, "per_page": count, "orientation": "landscape"},
        headers={"Authorization": f"Client-ID {key}"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    result_names: list[str] = []
    for photo in results[:count]:
        img_url = (photo.get("urls") or {}).get("regular")
        if not img_url:
            continue
        fname = f"unsplash_{hashlib.md5(img_url.encode(), usedforsecurity=False).hexdigest()[:10]}.jpg"
        dest = UPLOADS_DIR / fname
        if not dest.exists():
            img_r = _req.get(img_url, timeout=20, headers={"User-Agent": "HaehanAI/1.0"})
            img_r.raise_for_status()
            dest.write_bytes(img_r.content)
        # Unsplash Production 요건: 사용 시 download 엔드포인트 호출
        photo_id = photo.get("id")
        if photo_id:
            # Unsplash download 트리거 - 실패해도 이미지는 이미 다운로드됨(집계용 API일 뿐)
            with contextlib.suppress(Exception):
                _req.get(
                    f"{_UNSPLASH_API}/photos/{photo_id}/download",
                    headers={"Authorization": f"Client-ID {key}"},
                    timeout=5,
                )
        result_names.append(fname)
        time.sleep(0.1)

    if result_names:
        emit_event(
            "NAVER_BLOG_UNSPLASH",
            site="naver_blog",
            workflow="blog_media",
            status="resolved_live",
            risk="none",
            metadata={"topic": topic[:80], "query": query, "count": len(result_names)},
        )
    return result_names


def resolve_unsplash_images(topic: str, media: list[str], count: int = 3) -> list[str]:
    """media가 비어 있으면 Unsplash에서 이미지를 가져와 blog_uploads에 다운로드 후 파일명 반환.

    1. media가 이미 있으면 그대로 반환
    2. Unsplash 실시간 검색(API 키 있을 때) 우선 시도
    3. 실패 시 로컬 캐시(unsplash_images.json)로 폴백
    """
    if media:
        return media

    try:
        names = _unsplash_live_search(topic, count)
        if names:
            return names
    except Exception:  # noqa: BLE001
        pass

    return _resolve_unsplash_images_from_cache(topic, count)


def _resolve_unsplash_images_from_cache(topic: str, count: int = 3) -> list[str]:
    """Unsplash 실시간 검색 실패 시 폴백 — 로컬 캐시(unsplash_images.json)에서 선택.

    1. unsplash_images.json 로드 → topic 키워드 매칭 → 없으면 전체 순환
    2. URL → data/blog_uploads/unsplash_*.jpg 다운로드
    3. Unsplash 정책상 download_location 트리거
    """
    if not _UNSPLASH_CACHE.exists():
        return []

    try:
        import hashlib
        import time

        import requests as _req

        all_imgs: list[dict] = json.loads(_UNSPLASH_CACHE.read_text(encoding="utf-8")).get("images", [])
        if not all_imgs:
            return []

        # 키워드 매칭 (topic 단어 중 하나라도 query/desc에 포함)
        words = [w for w in topic.lower().split() if len(w) > 1]
        matched = [
            img for img in all_imgs if any(w in (img.get("query", "") + img.get("desc", "")).lower() for w in words)
        ] or all_imgs  # 매칭 없으면 전체 사용

        selected = [matched[i % len(matched)] for i in range(count)]
        result_names: list[str] = []

        for img in selected:
            url = img.get("url", "")
            if not url:
                continue
            fname = f"unsplash_{hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:10]}.jpg"
            dest = UPLOADS_DIR / fname
            if not dest.exists():
                r = _req.get(url, timeout=20, headers={"User-Agent": "HaehanAI/1.0"})
                r.raise_for_status()
                dest.write_bytes(r.content)
            # Unsplash 정책: 다운로드 트리거
            dl_loc = img.get("download_location", "")
            if dl_loc:
                try:
                    _req.get(dl_loc, headers={"Authorization": f"Client-ID {_unsplash_key()}"}, timeout=5)
                except Exception as e:  # noqa: BLE001 - 네이버 블로그 이미지(Unsplash) 다운로드/초안 목록/SEO 제안 라우터 - 실패 시 빈 목록/기본 분석값으로 폴백, 쓰기 실패는 draft 목록에서 빠질 뿐 발행 승인 로직과 무관
                    # Unsplash 정책상 download_location 통지는 실패해도 본 작업은 계속한다
                    _log.debug("[unsplash] download_location 통지 실패: %s", type(e).__name__)
            result_names.append(fname)
            time.sleep(0.1)

        emit_event(
            "NAVER_BLOG_UNSPLASH",
            site="naver_blog",
            workflow="blog_media",
            status="resolved",
            risk="none",
            metadata={"topic": topic[:80], "count": len(result_names), "files": result_names},
        )
        return result_names
    except Exception:  # noqa: BLE001 - 네이버 블로그 이미지(Unsplash) 다운로드/초안 목록/SEO 제안 라우터 - 실패 시 빈 목록/기본 분석값으로 폴백, 쓰기 실패는 draft 목록에서 빠질 뿐 발행 승인 로직과 무관
        return []
