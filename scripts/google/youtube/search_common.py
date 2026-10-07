"""Shared constants, path helpers, HTTP utilities, and small pure helpers.

This module is the only shared leaf.  All other leaves may import from here;
no leaf may import from another leaf.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root
from scripts.common import youtube_search_cache as _shared_cache
from scripts.common.http_retry import urlopen_with_dead_proxy_fallback as _urlopen_with_dead_proxy_fallback
from ai_orchestrator.core.security_utils import safe_preview

ROOT = repo_root()
REPORT_DIR = ROOT / "data" / "google_youtube_search_reports"
LATEST_SEARCH = ROOT / "data" / "google_youtube_search_latest.json"
LATEST_ANALYSIS = ROOT / "data" / "google_youtube_rank_analysis_latest.json"
LATEST_TOPIC_ANALYSIS = ROOT / "data" / "google_youtube_topic_analysis_latest.json"
LATEST_MARKET_RESEARCH = ROOT / "data" / "youtube_market_research_latest.json"
MARKET_RESEARCH_REPORT_DIR = ROOT / "docs" / "reports"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
WORD_RE = re.compile(r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣_+-]{1,}")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "you",
    "are",
    "from",
    "have",
    "will",
    "your",
    "그리고",
    "그래서",
    "합니다",
    "있는",
    "이런",
    "영상",
}
TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "beginner_overview": ("beginner", "basic", "intro", "입문", "기초", "초보"),
    "chatgpt_prompting": ("chatgpt", "gpt", "prompt", "챗gpt", "프롬프트"),
    "workflow_automation": ("automation", "workflow", "process", "업무", "자동화", "프로세스"),
    "spreadsheet_automation": ("excel", "sheets", "spreadsheet", "엑셀", "시트"),
    "nocode_automation": ("zapier", "make", "n8n", "nocode", "no-code", "노코드"),
    "agent_browser_automation": ("agent", "browser", "crawler", "scraping", "에이전트", "브라우저", "스크래핑"),
    "monetization_side_hustle": ("money", "profit", "side hustle", "수익", "부업", "돈"),
    "enterprise_productivity": ("enterprise", "productivity", "team", "기업", "생산성", "협업"),
    "smartstore_seller": (
        "smartstore",
        "스마트스토어",
        "네이버스마트스토어",
        "쇼핑몰",
        "상품등록",
        "상세페이지",
        "위탁판매",
    ),
    "commerce_marketing": ("commerce", "marketing", "seo", "마케팅", "상위노출", "키워드", "광고", "전환"),
    "global_sourcing": ("sourcing", "dropshipping", "구매대행", "사입", "위탁", "알리", "타오바오"),
}
TOPIC_KEYWORD_PRESETS: dict[str, tuple[str, ...]] = {
    "ai_work_automation": (
        "AI 업무 자동화",
        "챗GPT 업무 자동화",
        "엑셀 자동화 AI",
        "구글시트 자동화",
        "노코드 자동화",
        "n8n 자동화",
        "AI 에이전트 자동화",
    ),
    "smartstore": (
        "스마트스토어 시작",
        "스마트스토어 상품등록",
        "스마트스토어 상위노출",
        "네이버 스마트스토어 판매자",
        "스마트스토어 키워드",
        "스마트스토어 상세페이지",
        "스마트스토어 광고",
        "스마트스토어 위탁판매",
    ),
    "shopping_mall": (
        "쇼핑몰 창업",
        "쇼핑몰 상품등록",
        "쇼핑몰 마케팅",
        "쇼핑몰 SEO",
        "쇼핑몰 상위노출",
        "온라인 판매 키워드",
    ),
    "purchase_agency": (
        "구매대행 시작",
        "구매대행 상품소싱",
        "구매대행 스마트스토어",
        "타오바오 사입",
        "알리익스프레스 위탁판매",
        "위탁판매 상품소싱",
    ),
    "commerce_marketing": (
        "스마트스토어 마케팅",
        "네이버 쇼핑 상위노출",
        "상품명 키워드",
        "쇼핑몰 전환율",
        "쇼핑 광고 운영",
        "상세페이지 기획",
    ),
}
TOPIC_ALIASES: dict[str, str] = {
    "스마트스토어": "smartstore",
    "네이버스마트스토어": "smartstore",
    "쇼핑몰": "shopping_mall",
    "구매대행": "purchase_agency",
    "위탁판매": "purchase_agency",
    "마케팅": "commerce_marketing",
    "ai업무자동화": "ai_work_automation",
}


def build_public_signal_model() -> dict[str, Any]:
    """Describe what YouTube market research can and cannot know.

    This model is included in reports so downstream tools do not treat inferred
    opportunity scores as official YouTube search or watch demand.
    """
    return {
        "model": "public_signal_inference",
        "officially_available": [
            "public video search results for a supplied query",
            "public video metadata such as title, channel, published date, and description",
            "public video statistics when available, such as view, like, and comment counts",
            "caption availability hint through the official API",
        ],
        "not_officially_available": [
            "absolute YouTube search volume by keyword",
            "keyword click-through rate",
            "viewer watch history or audience-level behavior",
            "impressions, retention, and traffic-source data for videos we do not own",
            "stable global ranking for an arbitrary topic",
        ],
        "inferred_signals": [
            "observed search position per keyword at collection time",
            "repeated appearance across related keywords",
            "public popularity based on visible or API-provided counts",
            "topic fit from title, description, metadata, and optional transcript summary",
        ],
        "confidence_rule": (
            "Treat results as directional market signals. Confidence improves when a video "
            "appears across multiple related keywords, has public statistics, and has a "
            "transcript summary; it is not proof of absolute user demand."
        ),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_report(
    payload: dict[str, Any],
    path: Path | None = None,
    *,
    latest_path: Path = LATEST_SEARCH,
) -> tuple[dict[str, Any], Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    target = path or REPORT_DIR / f"google_youtube_search_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return payload, target


def _api_key(explicit: str | None = None) -> str:
    return (
        explicit
        or os.environ.get("YOUTUBE_DATA_API_KEY", "")
        or os.environ.get("YOUTUBE_API_KEY", "")
        or os.environ.get("GOOGLE_YOUTUBE_API_KEY", "")
    )


def _oauth_access_token() -> str | None:
    """저장된 OAuth 토큰을 갱신해서 반환. 없으면 None."""
    token_path = os.environ.get(
        "YOUTUBE_OAUTH_TOKEN_FILE",
        str(
            Path(__file__).resolve().parents[3]
            / "ai_orchestrator"
            / "storage"
            / "secrets"
            / "youtube_oauth_authorized_user.json"
        ),
    )
    if not Path(token_path).exists():
        return None
    try:
        t = json.loads(Path(token_path).read_text(encoding="utf-8"))
        data = urllib.parse.urlencode(
            {
                "client_id": t["client_id"],
                "client_secret": t["client_secret"],
                "refresh_token": t["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(
            t.get("token_uri", "https://oauth2.googleapis.com/token"),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read()).get("access_token")
    except Exception:  # noqa: BLE001 - 유튜브 검색 토큰/캐시 조회 공용 유틸 — 토큰 획득 실패나 SQLite 캐시 조회/저장 실패는 캐시미스로 간주해 None 반환 또는 무시, 쓰기 실패도 무시(캐시는 성능최적화용 부가기능)
        return None


def _get_json(url: str, params: dict[str, str | int]) -> dict[str, Any]:
    # OAuth 우선, 없으면 API 키
    access_token = _oauth_access_token()
    if access_token:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{url}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        )
    else:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(f"{url}?{query}", headers={"Accept": "application/json"})
    with _urlopen_with_dead_proxy_fallback(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


# scripts/youtube/research_search.py 와 동일한 캐시 DB(파일)를 공유한다.
# YouTube Search Queries per day 쿼터(100회/일)가 일반 쿼터(10,000회/일)보다
# 훨씬 낮아, 같은 쿼리를 반복 검색하면 시장조사 1회 실행만으로도 쉽게
# 소진된다. 두 검색 경로(단건 검색 / 시장조사 키워드 확장 검색)가 같은 DB를
# 공유하면 어느 경로로 먼저 검색됐든 캐시가 재사용된다.
# 정리(docs/defect_index.json #15, 2026-09-29): 실제 구현은
# scripts/common/youtube_search_cache.py 로 옮기고, 이 도메인의 기존
# import 지점(search.py 와 분석/점수/검색 leaf 등)이
# 계속 같은 이름으로 쓸 수 있게 여기서 별칭만 다시 내보낸다.
_search_cache_key = _shared_cache.cache_key
_search_cache_get = _shared_cache.cache_get
_search_cache_set = _shared_cache.cache_set


def build_search_url(query: str) -> str:
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)


def _base_payload(query: str, source: str, max_results: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "google_youtube_search",
        "query": safe_preview(query, limit=120),
        "source": source,
        "max_results": max_results,
        "state_change": False,
        "read_only": True,
        "no_click": True,
        "no_input": True,
        "no_submit": True,
        "cookie_export": False,
        "storage_export": False,
        "hidden_endpoint_scraping": False,
        "results": [],
    }


def _int_value(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    try:
        return int(float(text))
    except ValueError:
        return 0


def _metadata_number(values: Any, marker: str) -> int:
    import re as _re

    if not isinstance(values, list):
        return 0
    for value in values:
        text = str(value).lower().replace(",", "")
        if marker not in text:
            continue
        multiplier = 1
        if "k" in text:
            multiplier = 1_000
        elif "m" in text:
            multiplier = 1_000_000
        match = _re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            return int(float(match.group(1)) * multiplier)
    return 0


def _normalize_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for keyword in keywords:
        value = re.sub(r"\s+", " ", str(keyword or "")).strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized


def _top_keywords(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    words = [word for word in words if word not in STOPWORDS and len(word) > 1]
    return [{"keyword": word, "count": count} for word, count in Counter(words).most_common(limit)]
