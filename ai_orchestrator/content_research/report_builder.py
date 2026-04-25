"""Naver + YouTube 통합 콘텐츠 조사 리포트 빌더 (F-4S-4).

설계 원칙:
- read-only. 검색/메타 조회만 사용. 글쓰기/업로드/댓글/가입 흐름 절대 추가 금지.
- 네이버/유튜브 클라이언트는 mock_or_disabled 도 정상 결과로 취급. 키 없어도 리포트 구조 생성.
- API key / client_secret 은 절대 결과/로그/리포트에 포함하지 않는다.
- HTML 태그는 최소 정리(`<b>`, `</b>` 등 단순 태그 제거).
- 원문 응답 전체 보관 금지 — 통합 item 단위로만 저장.
- 한쪽 플랫폼 실패가 전체 FAIL 을 만들지 않는다.
- requests / browser / playwright import 금지.
"""
from __future__ import annotations

import csv
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ai_orchestrator.connectors import naver_search_api_client as naver_client
from ai_orchestrator.connectors import naver_search_api_config as naver_cfg_mod
from ai_orchestrator.connectors import youtube_data_api_client as yt_client
from ai_orchestrator.connectors import youtube_data_api_config as yt_cfg_mod

logger = logging.getLogger(__name__)


DEFAULT_NAVER_TYPES: Tuple[str, ...] = ("blog", "news", "cafearticle")
DEFAULT_NAVER_DISPLAY = 5
DEFAULT_YOUTUBE_MAX = 5

_HTML_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[A-Za-z0-9가-힣]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")

_STOPWORDS: frozenset = frozenset(
    {
        # 한국어 불용어 후보
        "그리고", "그러나", "하지만", "그래서", "또는", "또한",
        "이것", "저것", "그것", "여기", "거기", "저기",
        "관련", "정보", "방법", "소개", "이야기", "확인", "정리", "추천",
        "최신", "오늘", "어제", "내일",
        # 영어 불용어 후보
        "the", "a", "an", "and", "or", "of", "in", "on", "to", "for",
        "is", "are", "was", "were", "be", "been", "being",
        "with", "by", "from", "this", "that", "these", "those",
        "as", "at", "it", "its",
    }
)


# ---------------------------------------------------------------------------
# Pattern / scoring constants (F-4S-5)
# ---------------------------------------------------------------------------

PATTERN_QUESTION = "question"
PATTERN_NUMBERED = "numbered"
PATTERN_COMPARISON = "comparison"
PATTERN_PROBLEM_SOLUTION = "problem_solution"
PATTERN_REVIEW_CASE = "review_case"
PATTERN_LAW_STANDARD = "law_standard"
PATTERN_COST_ESTIMATE = "cost_estimate"
PATTERN_CHECKLIST = "checklist"

ALL_PATTERNS: Tuple[str, ...] = (
    PATTERN_QUESTION,
    PATTERN_NUMBERED,
    PATTERN_COMPARISON,
    PATTERN_PROBLEM_SOLUTION,
    PATTERN_REVIEW_CASE,
    PATTERN_LAW_STANDARD,
    PATTERN_COST_ESTIMATE,
    PATTERN_CHECKLIST,
)

_PATTERN_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    PATTERN_QUESTION: ("?", "왜", "어떻게", "어떤", "무엇", "언제", "어디", "누가", "how", "why", "what", "which", "when", "where"),
    PATTERN_COMPARISON: ("vs", "vs.", "대", "비교", "차이", "versus"),
    PATTERN_PROBLEM_SOLUTION: ("문제", "해결", "해법", "원인", "대처", "고치", "fix", "solve", "trouble"),
    PATTERN_REVIEW_CASE: ("후기", "리뷰", "사례", "경험", "써보", "써본", "review", "case"),
    PATTERN_LAW_STANDARD: ("법", "법령", "기준", "규정", "조항", "시행령", "고시", "표준", "regulation", "standard"),
    PATTERN_COST_ESTIMATE: ("비용", "가격", "견적", "단가", "예산", "원", "만원", "price", "cost", "budget"),
    PATTERN_CHECKLIST: ("체크리스트", "체크", "리스트", "checklist", "list", "필수", "준비물"),
}

_NUMBER_RE = re.compile(r"\d+")


def _coerce_dict_item(item: Any) -> Dict[str, Any]:
    """UnifiedItem 또는 dict 둘 다 허용해서 dict 형태로 정규화."""
    if isinstance(item, UnifiedItem):
        return item.to_dict()
    if isinstance(item, dict):
        return item
    return {}


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnifiedItem:
    platform: str
    source_type: str
    keyword: str
    title: str
    url: str
    summary: str
    published_at: Optional[str]
    channel_or_author: Optional[str]
    metrics: Dict[str, Optional[int]]
    raw_rank: int
    risk_flags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "source_type": self.source_type,
            "keyword": self.keyword,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published_at": self.published_at,
            "channel_or_author": self.channel_or_author,
            "metrics": dict(self.metrics),
            "raw_rank": self.raw_rank,
            "risk_flags": list(self.risk_flags),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_html(text: Any, *, max_len: Optional[int] = None) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    cleaned = _HTML_TAG.sub("", text)
    cleaned = html.unescape(cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if max_len is not None and len(cleaned) > max_len:
        cleaned = cleaned[: max_len].rstrip() + "…"
    return cleaned


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return None
    if isinstance(value, float):
        try:
            return int(value)
        except (OverflowError, ValueError):
            return None
    return None


def _ensure_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# normalize_keywords
# ---------------------------------------------------------------------------


def normalize_keywords(keywords: Optional[Iterable[Any]]) -> List[str]:
    if keywords is None:
        return []
    seen: List[str] = []
    seen_lower: set = set()
    for raw in keywords:
        if raw is None:
            continue
        text = _ensure_str(raw).strip()
        if not text:
            continue
        text = _WHITESPACE.sub(" ", text)
        key = text.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        seen.append(text)
    return seen


# ---------------------------------------------------------------------------
# Naver collection
# ---------------------------------------------------------------------------


def collect_naver_results(
    keyword: str,
    search_types: Optional[Sequence[str]] = None,
    display: int = DEFAULT_NAVER_DISPLAY,
    live: bool = False,
    *,
    config: Optional[naver_cfg_mod.NaverSearchApiConfig] = None,
    transport: Optional[naver_client.Transport] = None,
) -> Dict[str, Any]:
    if not keyword or not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("keyword is required")

    types_in = list(search_types) if search_types else list(DEFAULT_NAVER_TYPES)
    normalized_types: List[str] = []
    type_warnings: List[str] = []
    for t in types_in:
        try:
            normalized_types.append(naver_client.normalize_search_type(t))
        except ValueError as exc:
            type_warnings.append(f"naver_unknown_type:{t!r}:{exc}")

    results_by_type: Dict[str, Dict[str, Any]] = {}
    aggregated_warnings: List[str] = list(type_warnings)
    success_any = False
    failed_types: List[str] = []

    for nt in normalized_types:
        try:
            res = naver_client.search_naver(
                search_type=nt,
                query=keyword,
                display=display,
                start=1,
                sort=None,
                live=live,
                config=config,
                transport=transport,
            )
        except Exception as exc:  # pragma: no cover - defensive
            res = {
                "success": False,
                "mode": "live" if live else "mock_or_disabled",
                "search_type": nt,
                "query": keyword,
                "items": [],
                "error": f"exception:{type(exc).__name__}",
                "warnings": [],
            }
        results_by_type[nt] = res
        if res.get("success"):
            success_any = True
        else:
            failed_types.append(nt)
        for w in res.get("warnings") or []:
            aggregated_warnings.append(f"naver:{nt}:{w}")
        if res.get("error"):
            aggregated_warnings.append(f"naver:{nt}:error:{res['error']}")

    return {
        "keyword": keyword,
        "requested_types": types_in,
        "normalized_types": normalized_types,
        "results": results_by_type,
        "warnings": aggregated_warnings,
        "success_any": success_any,
        "failed_types": failed_types,
    }


# ---------------------------------------------------------------------------
# YouTube collection
# ---------------------------------------------------------------------------


def collect_youtube_results(
    keyword: str,
    max_results: int = DEFAULT_YOUTUBE_MAX,
    with_details: bool = False,
    live: bool = False,
    *,
    config: Optional[yt_cfg_mod.YoutubeDataApiConfig] = None,
    search_transport: Optional[yt_client.Transport] = None,
    details_transport: Optional[yt_client.Transport] = None,
) -> Dict[str, Any]:
    if not keyword or not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("keyword is required")

    warnings: List[str] = []
    try:
        search_res = yt_client.search_videos(
            query=keyword,
            max_results=max_results,
            order="relevance",
            published_after=None,
            live=live,
            config=config,
            transport=search_transport,
        )
    except Exception as exc:  # pragma: no cover - defensive
        search_res = {
            "success": False,
            "mode": "live" if live else "mock_or_disabled",
            "kind": "search",
            "query": keyword,
            "items": [],
            "error": f"exception:{type(exc).__name__}",
            "warnings": [],
        }

    for w in search_res.get("warnings") or []:
        warnings.append(f"youtube:search:{w}")
    if search_res.get("error"):
        warnings.append(f"youtube:search:error:{search_res['error']}")

    details_res: Optional[Dict[str, Any]] = None
    if with_details and search_res.get("success"):
        ids: List[str] = []
        for it in search_res.get("items") or []:
            vid = it.get("videoId") if isinstance(it, dict) else None
            if vid:
                ids.append(str(vid))
        if ids:
            try:
                details_res = yt_client.get_video_details(
                    video_ids=ids,
                    live=live,
                    config=config,
                    transport=details_transport,
                )
            except Exception as exc:  # pragma: no cover - defensive
                details_res = {
                    "success": False,
                    "mode": "live" if live else "mock_or_disabled",
                    "kind": "videos",
                    "video_ids": ids,
                    "items": [],
                    "error": f"exception:{type(exc).__name__}",
                    "warnings": [],
                }
            for w in details_res.get("warnings") or []:
                warnings.append(f"youtube:videos:{w}")
            if details_res.get("error"):
                warnings.append(f"youtube:videos:error:{details_res['error']}")

    return {
        "keyword": keyword,
        "max_results": max_results,
        "with_details": bool(with_details),
        "search": search_res,
        "details": details_res,
        "warnings": warnings,
        "success_any": bool(search_res.get("success")),
    }


# ---------------------------------------------------------------------------
# Unified item building
# ---------------------------------------------------------------------------


def _build_naver_unified(naver_block: Dict[str, Any]) -> List[UnifiedItem]:
    items: List[UnifiedItem] = []
    keyword = _ensure_str(naver_block.get("keyword"))
    results = naver_block.get("results") or {}
    if not isinstance(results, dict):
        return items
    for source_type, payload in results.items():
        if not isinstance(payload, dict):
            continue
        raw_items = payload.get("items") or []
        if not isinstance(raw_items, list):
            continue
        for idx, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                continue
            title = _strip_html(raw.get("title"))
            url = _ensure_str(raw.get("link")).strip()
            summary = _strip_html(raw.get("description"), max_len=300)
            published = (
                raw.get("postdate")
                or raw.get("pubDate")
                or None
            )
            channel = (
                raw.get("bloggername")
                or raw.get("cafename")
                or raw.get("mallName")
                or None
            )
            risk_flags: List[str] = []
            if not title:
                risk_flags.append("missing_title")
            if not url:
                risk_flags.append("missing_url")
            items.append(
                UnifiedItem(
                    platform="naver",
                    source_type=source_type,
                    keyword=keyword,
                    title=title,
                    url=url,
                    summary=summary,
                    published_at=_ensure_str(published) if published else None,
                    channel_or_author=_ensure_str(channel) if channel else None,
                    metrics={"view_count": None, "like_count": None, "comment_count": None},
                    raw_rank=idx,
                    risk_flags=risk_flags,
                )
            )
    return items


def _build_youtube_unified(youtube_block: Dict[str, Any]) -> List[UnifiedItem]:
    items: List[UnifiedItem] = []
    keyword = _ensure_str(youtube_block.get("keyword"))
    search = youtube_block.get("search") or {}
    details = youtube_block.get("details") or {}

    detail_by_id: Dict[str, Dict[str, Any]] = {}
    if isinstance(details, dict):
        for d in details.get("items") or []:
            if isinstance(d, dict) and d.get("videoId"):
                detail_by_id[str(d["videoId"])] = d

    raw_items = search.get("items") or []
    if not isinstance(raw_items, list):
        return items

    for idx, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            continue
        video_id = _ensure_str(raw.get("videoId")).strip()
        title = _strip_html(raw.get("title"))
        summary = _strip_html(raw.get("description"), max_len=300)
        url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        channel = raw.get("channelTitle") or None
        published = raw.get("publishedAt") or None

        det = detail_by_id.get(video_id) if video_id else None
        if det:
            view = _to_int_or_none(det.get("viewCount"))
            like = _to_int_or_none(det.get("likeCount"))
            comment = _to_int_or_none(det.get("commentCount"))
            if det.get("publishedAt"):
                published = det.get("publishedAt") or published
            if det.get("channelTitle"):
                channel = det.get("channelTitle") or channel
        else:
            view = like = comment = None

        risk_flags: List[str] = []
        if not title:
            risk_flags.append("missing_title")
        if not video_id:
            risk_flags.append("missing_video_id")

        items.append(
            UnifiedItem(
                platform="youtube",
                source_type="youtube_video",
                keyword=keyword,
                title=title,
                url=url,
                summary=summary,
                published_at=_ensure_str(published) if published else None,
                channel_or_author=_ensure_str(channel) if channel else None,
                metrics={"view_count": view, "like_count": like, "comment_count": comment},
                raw_rank=idx,
                risk_flags=risk_flags,
            )
        )
    return items


def build_unified_items(
    naver_results: Optional[Dict[str, Any]],
    youtube_results: Optional[Dict[str, Any]],
) -> List[UnifiedItem]:
    items: List[UnifiedItem] = []
    if naver_results:
        items.extend(_build_naver_unified(naver_results))
    if youtube_results:
        items.extend(_build_youtube_unified(youtube_results))
    return items


# ---------------------------------------------------------------------------
# Summary / extraction / ideas
# ---------------------------------------------------------------------------


def summarize_unified_items(items: Sequence[UnifiedItem]) -> Dict[str, Any]:
    naver_items = [it for it in items if it.platform == "naver"]
    youtube_items = [it for it in items if it.platform == "youtube"]
    by_source: Dict[str, int] = {}
    for it in items:
        by_source[it.source_type] = by_source.get(it.source_type, 0) + 1
    risk_count = sum(1 for it in items if it.risk_flags)
    return {
        "total_items": len(items),
        "naver_items": len(naver_items),
        "youtube_items": len(youtube_items),
        "items_by_source_type": by_source,
        "items_with_risk_flag": risk_count,
    }


def extract_title_terms(
    items: Sequence[UnifiedItem],
    top_n: int = 20,
) -> List[Tuple[str, int]]:
    counter: Dict[str, int] = {}
    for it in items:
        for token in _WORD.findall(it.title or ""):
            t = token.strip()
            if not t:
                continue
            t_lower = t.lower()
            if t_lower in _STOPWORDS:
                continue
            if len(t) <= 1:
                continue
            counter[t] = counter.get(t, 0) + 1
    ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    if top_n is None or top_n <= 0:
        return ordered
    return ordered[:top_n]


def build_content_ideas(
    items: Sequence[UnifiedItem],
    keywords: Sequence[str],
    *,
    max_ideas: int = 10,
) -> List[Dict[str, Any]]:
    if not items:
        return []
    terms = [t for t, _ in extract_title_terms(items, top_n=12)]
    norm_keywords = [k for k in keywords if k]
    seeds: List[str] = []
    for kw in norm_keywords:
        seeds.append(kw)
    for t in terms:
        if t not in seeds:
            seeds.append(t)
    ideas: List[Dict[str, Any]] = []
    templates = (
        "{seed} 핵심 정리 — 일반인이 가장 자주 묻는 3가지",
        "{seed} 실제 사례 비교 — 잘된 케이스 vs 실패 케이스",
        "{seed} 셀프 체크리스트 — 의뢰 전 알아둘 5가지",
        "{seed} 비용/일정 가이드 — 견적 받을 때 확인 포인트",
        "{seed} 영상 인서트용 짧은 설명 — 30초 핵심 메시지",
    )
    for i, seed in enumerate(seeds[:max_ideas]):
        template = templates[i % len(templates)]
        ideas.append(
            {
                "seed": seed,
                "title": template.format(seed=seed),
                "format_hint": "shorts" if i % 2 else "long_form",
                "rank": i + 1,
            }
        )
    return ideas[:max_ideas]


# ---------------------------------------------------------------------------
# Pattern detection (F-4S-5)
# ---------------------------------------------------------------------------


def _title_text(item: Dict[str, Any]) -> str:
    return _ensure_str(item.get("title")).strip()


def _summary_text(item: Dict[str, Any]) -> str:
    return _ensure_str(item.get("summary")).strip()


def detect_item_patterns(item: Any) -> List[str]:
    """단일 item 의 제목/요약에서 패턴 라벨 목록을 추출."""
    src = _coerce_dict_item(item)
    title = _title_text(src)
    summary = _summary_text(src)
    haystack = f"{title} {summary}".lower()

    matched: List[str] = []
    if "?" in title or any(kw in haystack for kw in _PATTERN_KEYWORDS[PATTERN_QUESTION] if kw):
        matched.append(PATTERN_QUESTION)
    if _NUMBER_RE.search(title):
        matched.append(PATTERN_NUMBERED)
    for label in (
        PATTERN_COMPARISON,
        PATTERN_PROBLEM_SOLUTION,
        PATTERN_REVIEW_CASE,
        PATTERN_LAW_STANDARD,
        PATTERN_COST_ESTIMATE,
        PATTERN_CHECKLIST,
    ):
        for kw in _PATTERN_KEYWORDS[label]:
            if not kw:
                continue
            if kw.lower() in haystack:
                matched.append(label)
                break
    seen: List[str] = []
    for p in matched:
        if p not in seen:
            seen.append(p)
    return seen


def detect_content_patterns(items: Sequence[Any]) -> Dict[str, Any]:
    """전체 item 에 대해 패턴 빈도/예시 url 을 산출."""
    counts: Dict[str, int] = {p: 0 for p in ALL_PATTERNS}
    examples: Dict[str, List[Dict[str, str]]] = {p: [] for p in ALL_PATTERNS}
    per_item: List[Dict[str, Any]] = []
    for item in items or []:
        src = _coerce_dict_item(item)
        labels = detect_item_patterns(src)
        per_item.append(
            {
                "title": _title_text(src),
                "url": _ensure_str(src.get("url")),
                "patterns": labels,
            }
        )
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
            if len(examples[label]) < 3:
                examples[label].append(
                    {
                        "title": _title_text(src),
                        "url": _ensure_str(src.get("url")),
                        "platform": _ensure_str(src.get("platform")),
                        "source_type": _ensure_str(src.get("source_type")),
                    }
                )
    total = max(1, len(items or []))
    distribution: Dict[str, Dict[str, Any]] = {}
    for label in ALL_PATTERNS:
        distribution[label] = {
            "count": counts.get(label, 0),
            "ratio": round(counts.get(label, 0) / total, 4),
            "examples": list(examples.get(label, [])),
        }
    return {
        "counts": dict(counts),
        "distribution": distribution,
        "per_item": per_item,
        "total_items": len(items or []),
    }


# ---------------------------------------------------------------------------
# Scoring & ranking (F-4S-5)
# ---------------------------------------------------------------------------


def _keyword_match_count(text: str, keywords: Sequence[str]) -> int:
    if not text or not keywords:
        return 0
    lower = text.lower()
    matched = 0
    for kw in keywords:
        kw_str = _ensure_str(kw).strip().lower()
        if not kw_str:
            continue
        if kw_str in lower:
            matched += 1
    return matched


def _recency_score(published_at: Optional[str], *, now_utc: Optional[datetime] = None) -> float:
    """ISO8601 또는 yyyymmdd 형태 게시일자 → [0..1] recency score.
    파싱 실패/None 이면 0 반환. 1년 이내 1.0 → 3년 이상 0.0 선형감쇠.
    """
    if not published_at:
        return 0.0
    txt = _ensure_str(published_at).strip()
    if not txt:
        return 0.0
    parsed: Optional[datetime] = None
    try:
        if txt.endswith("Z"):
            parsed = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        elif "T" in txt:
            parsed = datetime.fromisoformat(txt)
        elif len(txt) == 8 and txt.isdigit():
            parsed = datetime(int(txt[0:4]), int(txt[4:6]), int(txt[6:8]), tzinfo=timezone.utc)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = now_utc or datetime.now(timezone.utc)
    age_days = max(0.0, (now - parsed).total_seconds() / 86400.0)
    if age_days <= 365:
        return 1.0
    if age_days >= 365 * 3:
        return 0.0
    span = (365 * 3) - 365
    return round(max(0.0, 1.0 - (age_days - 365) / span), 4)


def _log_scale(value: Optional[int]) -> float:
    if not value or value <= 0:
        return 0.0
    import math
    return round(math.log10(value + 1), 4)


def score_content_items(
    items: Sequence[Any],
    keywords: Optional[Sequence[str]] = None,
    *,
    now_utc: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """각 item 에 대해 platform 별 점수 dict 부여. 원본 item 은 변경하지 않는다."""
    norm_keywords = list(keywords or [])
    scored: List[Dict[str, Any]] = []
    for item in items or []:
        src = _coerce_dict_item(item)
        title = _title_text(src)
        summary = _summary_text(src)
        title_match = _keyword_match_count(title, norm_keywords)
        summary_match = _keyword_match_count(summary, norm_keywords)
        recency = _recency_score(src.get("published_at"), now_utc=now_utc)
        metrics = src.get("metrics") or {}
        platform = _ensure_str(src.get("platform"))
        view_log = _log_scale(metrics.get("view_count"))
        like_log = _log_scale(metrics.get("like_count"))
        comment_log = _log_scale(metrics.get("comment_count"))
        rank_penalty = 1.0 / (1 + max(0, _to_int_or_none(src.get("raw_rank")) or 0))
        if platform == "youtube":
            base = view_log * 1.0 + like_log * 0.6 + comment_log * 0.4
            relevance = title_match * 1.2 + summary_match * 0.4
            score = round(base + relevance + recency * 1.0 + rank_penalty * 0.3, 4)
        elif platform == "naver":
            base = title_match * 1.5 + summary_match * 0.5
            score = round(base + recency * 0.8 + rank_penalty * 1.2, 4)
        else:
            score = round(title_match * 1.0 + summary_match * 0.3 + rank_penalty, 4)
        scored.append(
            {
                "item": src,
                "score": score,
                "components": {
                    "title_match": title_match,
                    "summary_match": summary_match,
                    "recency": recency,
                    "view_log": view_log,
                    "like_log": like_log,
                    "comment_log": comment_log,
                    "rank_penalty": round(rank_penalty, 4),
                },
            }
        )
    return scored


def rank_youtube_candidates(
    items: Sequence[Any],
    keywords: Optional[Sequence[str]] = None,
    *,
    top_n: int = 10,
    now_utc: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    yt_items = [it for it in (items or []) if _coerce_dict_item(it).get("platform") == "youtube"]
    scored = score_content_items(yt_items, keywords, now_utc=now_utc)
    scored.sort(key=lambda kv: (-kv["score"], _ensure_str(kv["item"].get("title"))))
    if top_n is None or top_n <= 0:
        return scored
    return scored[:top_n]


def rank_naver_candidates(
    items: Sequence[Any],
    keywords: Optional[Sequence[str]] = None,
    *,
    top_n: int = 10,
    by_source_type: bool = True,
    now_utc: Optional[datetime] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """source_type 별로 분리된 ranking 을 반환. by_source_type=False 면 단일 리스트."""
    naver_items = [it for it in (items or []) if _coerce_dict_item(it).get("platform") == "naver"]
    if not by_source_type:
        scored = score_content_items(naver_items, keywords, now_utc=now_utc)
        scored.sort(key=lambda kv: (-kv["score"], _ensure_str(kv["item"].get("title"))))
        return {"all": scored[:top_n] if top_n and top_n > 0 else scored}

    grouped: Dict[str, List[Any]] = {}
    for it in naver_items:
        src = _coerce_dict_item(it)
        st = _ensure_str(src.get("source_type")) or "unknown"
        grouped.setdefault(st, []).append(it)

    out: Dict[str, List[Dict[str, Any]]] = {}
    for st, group in grouped.items():
        scored = score_content_items(group, keywords, now_utc=now_utc)
        scored.sort(key=lambda kv: (-kv["score"], _ensure_str(kv["item"].get("title"))))
        out[st] = scored[:top_n] if top_n and top_n > 0 else scored
    return out


# ---------------------------------------------------------------------------
# Platform strategy (F-4S-5)
# ---------------------------------------------------------------------------


def build_platform_strategy(
    summary: Dict[str, Any],
    ranked_items: Optional[Dict[str, Any]] = None,
    patterns: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """수집된 결과 분포에 기반해 플랫폼별 권장 전략 생성."""
    summary = summary or {}
    ranked_items = ranked_items or {}
    patterns = patterns or {}
    counts = patterns.get("counts") or {}

    naver_count = int(summary.get("naver_items") or 0)
    youtube_count = int(summary.get("youtube_items") or 0)
    by_source = summary.get("items_by_source_type") or {}

    cafe_count = int(by_source.get("cafearticle") or 0)
    blog_count = int(by_source.get("blog") or 0)
    news_count = int(by_source.get("news") or 0)

    youtube_focus: List[str] = []
    if counts.get(PATTERN_QUESTION):
        youtube_focus.append("질문형 제목 활용 — Shorts hook 으로 적합")
    if counts.get(PATTERN_NUMBERED):
        youtube_focus.append("숫자형 제목 다수 — '5가지/3가지' 형태 long-form 추천")
    if counts.get(PATTERN_COMPARISON):
        youtube_focus.append("비교형 키워드 존재 — A vs B 형식 비교 영상 권장")
    if counts.get(PATTERN_REVIEW_CASE):
        youtube_focus.append("후기/사례 콘텐츠 다수 — 실 케이스 인터뷰/리뷰 영상")
    if not youtube_focus:
        youtube_focus.append("아직 충분한 데이터 없음 — live key 등록 후 재실행 권장")

    naver_focus: List[str] = []
    if blog_count >= news_count and blog_count > 0:
        naver_focus.append("블로그 비중 우세 — 경험형/가이드형 장문 포스트 권장")
    if cafe_count > 0:
        naver_focus.append("카페 글 존재 — Q&A 답변형 / 후기 정리형으로 재가공 가능")
    if news_count > 0:
        naver_focus.append("뉴스 노출 존재 — 시의성 키워드로 재해석 콘텐츠 권장")
    if counts.get(PATTERN_LAW_STANDARD):
        naver_focus.append("법령/기준형 콘텐츠 다수 — 정확성 검증된 standard 가이드 페이지로 강화")
    if counts.get(PATTERN_COST_ESTIMATE):
        naver_focus.append("비용/견적형 키워드 존재 — '의뢰 전 체크' 견적 가이드 포스트")
    if not naver_focus:
        naver_focus.append("아직 충분한 데이터 없음 — live key 등록 후 재실행 권장")

    return {
        "youtube": {
            "item_count": youtube_count,
            "focus_recommendations": youtube_focus,
            "recommended_formats": ["short", "long_form"] if youtube_count >= 5 else ["short"],
        },
        "naver": {
            "item_count": naver_count,
            "by_source_type": dict(by_source),
            "focus_recommendations": naver_focus,
            "recommended_formats": ["blog_long", "cafe_qna"] if cafe_count > 0 else ["blog_long"],
        },
        "cross_platform": {
            "shared_patterns": [p for p, c in counts.items() if c > 0],
            "note": "동일 키워드를 네이버/유튜브 양쪽에서 변형 재사용해 노출면을 넓힐 것",
        },
    }


# ---------------------------------------------------------------------------
# LTX video brief (F-4S-5)
# ---------------------------------------------------------------------------


def _infer_target_platform(item: Dict[str, Any]) -> str:
    platform = _ensure_str(item.get("platform"))
    source_type = _ensure_str(item.get("source_type"))
    title = _title_text(item)
    if platform == "youtube":
        if any(tok in title.lower() for tok in ("#shorts", "shorts", "쇼츠", "1분", "30초")):
            return "youtube_short"
        return "youtube_long"
    if source_type == "cafearticle":
        return "cafe_post"
    return "naver_blog"


def _safe_short_title(text: str, *, max_len: int = 50) -> str:
    if not text:
        return "(no title)"
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def _brief_scene_ideas(seed_title: str, target_platform: str) -> List[str]:
    base = [
        f"오프닝 — '{_safe_short_title(seed_title, max_len=30)}' 한 줄 hook",
        "핵심 포인트 3가지 자막 강조",
        "현장/예시 b-roll 또는 도식 인서트",
        "마무리 CTA — '댓글 대신 자료 다운로드 안내' (구독/가입 유도 금지)",
    ]
    if target_platform == "youtube_short":
        return base[:3] + ["8~12초 쇼츠 컷 편집"]
    if target_platform == "youtube_long":
        return base + ["챕터 구분 / 챕터별 자막 키워드 노출"]
    return ["대표 이미지 1장", "본문 핵심 3단 구성"] + base[1:3]


def _brief_subtitle_points(item: Dict[str, Any], keywords: Sequence[str]) -> List[str]:
    title = _title_text(item)
    summary = _summary_text(item)
    points: List[str] = []
    if title:
        points.append(f"핵심 메시지: {_safe_short_title(title, max_len=60)}")
    if summary:
        points.append(f"보조 요약: {_safe_short_title(summary, max_len=80)}")
    for kw in keywords:
        kw_str = _ensure_str(kw).strip()
        if kw_str:
            points.append(f"키워드 강조: {kw_str}")
            break
    if not points:
        points.append("핵심 메시지: (제목 미상 — 시각 자료로 보완)")
    return points


def _brief_risk_notes(item: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    risk_flags = item.get("risk_flags") or []
    if "missing_title" in risk_flags:
        notes.append("원본 제목 누락 — 자막/대본 작성 시 sourced fact 보강 필요")
    if "missing_url" in risk_flags or "missing_video_id" in risk_flags:
        notes.append("출처 URL 누락 — 인용 시 reference 미확보 위험")
    notes.append("read-only 분석 결과 기반. 댓글/업로드/가입 흐름 절대 추가 금지")
    notes.append("원본 영상/포스트 캡처 직접 사용 시 저작권/초상권 별도 검토")
    return notes


def build_ltx_video_briefs(
    items: Sequence[Any],
    keywords: Sequence[str],
    *,
    max_count: int = 5,
    now_utc: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """상위 score item 기준 LTX 영상 brief 생성."""
    if not items:
        return []
    scored = score_content_items(items, keywords, now_utc=now_utc)
    scored.sort(key=lambda kv: (-kv["score"], _ensure_str(kv["item"].get("title"))))
    briefs: List[Dict[str, Any]] = []
    for entry in scored:
        src = entry["item"]
        title = _title_text(src)
        if not title:
            continue
        target = _infer_target_platform(src)
        brief = {
            "title": _safe_short_title(title, max_len=80),
            "hook": f"왜 지금 '{_safe_short_title(title, max_len=30)}' 인가?",
            "scene_ideas": _brief_scene_ideas(title, target),
            "subtitle_points": _brief_subtitle_points(src, keywords),
            "source_basis": [
                {
                    "platform": _ensure_str(src.get("platform")),
                    "source_type": _ensure_str(src.get("source_type")),
                    "url": _ensure_str(src.get("url")),
                    "title": title,
                }
            ],
            "target_platform": target,
            "risk_notes": _brief_risk_notes(src),
            "score": entry["score"],
        }
        briefs.append(brief)
        if max_count and len(briefs) >= max_count:
            break
    return briefs


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _format_metric(value: Optional[int]) -> str:
    if value is None:
        return "-"
    try:
        return f"{value:,}"
    except (TypeError, ValueError):
        return str(value)


def render_markdown_report(report: Dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    keywords = report.get("keywords") or []
    items: List[Dict[str, Any]] = report.get("items") or []
    ideas = report.get("content_ideas") or []
    title_terms = report.get("title_terms") or []
    warnings = report.get("warnings") or []
    mode = report.get("mode") or "dry_run"
    generated_at = report.get("generated_at") or ""
    next_actions = report.get("next_actions") or []
    analysis = report.get("analysis") or {}
    ranked_youtube = analysis.get("ranked_youtube") or []
    ranked_naver_by_st: Dict[str, List[Dict[str, Any]]] = analysis.get("ranked_naver") or {}
    patterns = analysis.get("patterns") or {}
    strategy = analysis.get("platform_strategy") or {}
    ltx_briefs = report.get("ltx_video_briefs") or []

    lines: List[str] = []
    lines.append("# 콘텐츠 조사 리포트")
    lines.append("")
    lines.append("## 요약")
    lines.append(f"- 생성 시각: {generated_at}")
    lines.append(f"- 모드: {mode}")
    lines.append(f"- 키워드: {', '.join(keywords) if keywords else '-'}")
    lines.append(f"- 총 수집 item: {summary.get('total_items', 0)}")
    lines.append(f"- 네이버 items: {summary.get('naver_items', 0)}")
    lines.append(f"- 유튜브 items: {summary.get('youtube_items', 0)}")
    lines.append(f"- 경고 수: {len(warnings)}")
    lines.append("")

    lines.append("## 플랫폼별 결과")
    by_source = summary.get("items_by_source_type") or {}
    if not by_source:
        lines.append("- (수집된 항목 없음)")
    else:
        for src, cnt in sorted(by_source.items()):
            lines.append(f"- {src}: {cnt}")
    lines.append("")

    lines.append("## 상위 노출/반응 후보")
    if not items:
        lines.append("- (없음)")
    else:
        sortable = []
        for it in items:
            metrics = it.get("metrics") or {}
            view = metrics.get("view_count") or 0
            sortable.append((view, it))
        sortable.sort(key=lambda kv: kv[0], reverse=True)
        for _, it in sortable[:10]:
            metrics = it.get("metrics") or {}
            lines.append(
                f"- [{it.get('platform')}/{it.get('source_type')}] {it.get('title') or '(no title)'} "
                f"— views={_format_metric(metrics.get('view_count'))}, "
                f"likes={_format_metric(metrics.get('like_count'))}, "
                f"comments={_format_metric(metrics.get('comment_count'))} "
                f"({it.get('url') or '-'})"
            )
    lines.append("")

    lines.append("## 제목 키워드 빈도")
    if not title_terms:
        lines.append("- (수집된 제목 없음)")
    else:
        for term, count in title_terms[:20]:
            lines.append(f"- {term}: {count}")
    lines.append("")

    lines.append("## 영상 소재 후보")
    yt_items = [it for it in items if it.get("platform") == "youtube"]
    if not yt_items:
        lines.append("- (유튜브 결과 없음)")
    else:
        for it in yt_items[:10]:
            metrics = it.get("metrics") or {}
            lines.append(
                f"- {it.get('title') or '(no title)'} "
                f"({it.get('channel_or_author') or '-'}) "
                f"views={_format_metric(metrics.get('view_count'))} "
                f"— {it.get('url') or '-'}"
            )
    lines.append("")

    lines.append("## LTX 영상 제작 아이디어")
    if not ideas:
        lines.append("- (콘텐츠 부족으로 아이디어 미생성)")
    else:
        for idea in ideas:
            lines.append(
                f"- [{idea.get('format_hint')}] {idea.get('title')}  (seed={idea.get('seed')})"
            )
    lines.append("")

    lines.append("## YouTube 후보 랭킹")
    if not ranked_youtube:
        lines.append("- (유튜브 후보 없음)")
    else:
        for entry in ranked_youtube[:10]:
            it = entry.get("item") or {}
            metrics = it.get("metrics") or {}
            lines.append(
                f"- score={entry.get('score')} {_safe_short_title(_ensure_str(it.get('title')), max_len=60)} "
                f"— views={_format_metric(metrics.get('view_count'))} "
                f"likes={_format_metric(metrics.get('like_count'))} "
                f"({it.get('url') or '-'})"
            )
    lines.append("")

    lines.append("## Naver 후보 랭킹 (source_type 별)")
    if not ranked_naver_by_st:
        lines.append("- (네이버 후보 없음)")
    else:
        for st, entries in sorted(ranked_naver_by_st.items()):
            lines.append(f"### {st}")
            if not entries:
                lines.append("- (없음)")
                continue
            for entry in entries[:5]:
                it = entry.get("item") or {}
                lines.append(
                    f"- score={entry.get('score')} {_safe_short_title(_ensure_str(it.get('title')), max_len=60)} "
                    f"({it.get('url') or '-'})"
                )
    lines.append("")

    lines.append("## 콘텐츠 패턴 분포")
    distribution = patterns.get("distribution") or {}
    if not distribution:
        lines.append("- (패턴 분석 결과 없음)")
    else:
        for label in ALL_PATTERNS:
            entry = distribution.get(label) or {}
            cnt = entry.get("count", 0)
            ratio = entry.get("ratio", 0)
            lines.append(f"- {label}: count={cnt} ratio={ratio}")
    lines.append("")

    lines.append("## 플랫폼별 권장 전략")
    if not strategy:
        lines.append("- (전략 산출 결과 없음)")
    else:
        for plat in ("youtube", "naver"):
            block = strategy.get(plat) or {}
            lines.append(f"### {plat}")
            for rec in block.get("focus_recommendations") or []:
                lines.append(f"- {rec}")
            formats = block.get("recommended_formats") or []
            if formats:
                lines.append(f"- 추천 포맷: {', '.join(formats)}")
        cross = strategy.get("cross_platform") or {}
        if cross:
            lines.append("### cross_platform")
            shared = cross.get("shared_patterns") or []
            if shared:
                lines.append(f"- 공통 패턴: {', '.join(shared)}")
            note = cross.get("note")
            if note:
                lines.append(f"- {note}")
    lines.append("")

    lines.append("## LTX 영상 brief")
    if not ltx_briefs:
        lines.append("- (brief 미생성)")
    else:
        for i, brief in enumerate(ltx_briefs, start=1):
            lines.append(
                f"### {i}. [{brief.get('target_platform')}] {brief.get('title')}"
            )
            lines.append(f"- hook: {brief.get('hook')}")
            scenes = brief.get("scene_ideas") or []
            if scenes:
                lines.append(f"- scene_ideas: {' | '.join(scenes)}")
            subs = brief.get("subtitle_points") or []
            if subs:
                lines.append(f"- subtitle_points: {' | '.join(subs)}")
            sources = brief.get("source_basis") or []
            for src in sources:
                lines.append(
                    f"- source: [{src.get('platform')}/{src.get('source_type')}] {src.get('url') or '-'}"
                )
            risks = brief.get("risk_notes") or []
            for r in risks:
                lines.append(f"- risk: {r}")
    lines.append("")

    lines.append("## 경고 및 제한")
    if not warnings:
        lines.append("- (없음)")
    else:
        for w in warnings:
            lines.append(f"- {w}")
    lines.append("")

    lines.append("## 다음 조치")
    if not next_actions:
        lines.append("- 키 등록 후 --live 모드로 재실행")
        lines.append("- 상위 후보 검토 후 LTX 제작 큐에 등록")
    else:
        for act in next_actions:
            lines.append(f"- {act}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Build full report dict
# ---------------------------------------------------------------------------


def build_report(
    keywords: Sequence[str],
    *,
    naver_blocks: Sequence[Dict[str, Any]],
    youtube_blocks: Sequence[Dict[str, Any]],
    mode: str,
    platforms_attempted: Sequence[str],
    platforms_live: Sequence[str],
    extra_warnings: Optional[Sequence[str]] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    items: List[UnifiedItem] = []
    warnings: List[str] = list(extra_warnings or [])

    naver_block_by_kw: Dict[str, Dict[str, Any]] = {}
    for blk in naver_blocks:
        kw = _ensure_str(blk.get("keyword"))
        if kw:
            naver_block_by_kw[kw] = blk
        warnings.extend(blk.get("warnings") or [])

    youtube_block_by_kw: Dict[str, Dict[str, Any]] = {}
    for blk in youtube_blocks:
        kw = _ensure_str(blk.get("keyword"))
        if kw:
            youtube_block_by_kw[kw] = blk
        warnings.extend(blk.get("warnings") or [])

    for kw in keywords:
        items.extend(
            build_unified_items(
                naver_block_by_kw.get(kw),
                youtube_block_by_kw.get(kw),
            )
        )

    summary = summarize_unified_items(items)
    title_terms = extract_title_terms(items, top_n=20)
    ideas = build_content_ideas(items, keywords)
    item_dicts = [it.to_dict() for it in items]

    ranked_yt = rank_youtube_candidates(item_dicts, keywords, top_n=10)
    ranked_naver = rank_naver_candidates(item_dicts, keywords, top_n=10, by_source_type=True)
    patterns = detect_content_patterns(item_dicts)
    strategy = build_platform_strategy(
        {
            **summary,
            "keywords_count": len(list(keywords)),
        },
        ranked_items={"youtube": ranked_yt, "naver": ranked_naver},
        patterns=patterns,
    )
    ltx_briefs = build_ltx_video_briefs(item_dicts, keywords, max_count=5)

    report = {
        "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "keywords": list(keywords),
        "platforms_attempted": list(platforms_attempted),
        "platforms_live": list(platforms_live),
        "summary": {
            **summary,
            "keywords_count": len(list(keywords)),
            "platforms_attempted": list(platforms_attempted),
            "platforms_live": list(platforms_live),
            "warnings_count": len(warnings),
            "mode": mode,
        },
        "items": item_dicts,
        "title_terms": [list(pair) for pair in title_terms],
        "content_ideas": ideas,
        "analysis": {
            "ranked_youtube": ranked_yt,
            "ranked_naver": ranked_naver,
            "patterns": patterns,
            "platform_strategy": strategy,
        },
        "ltx_video_briefs": ltx_briefs,
        "warnings": warnings,
        "next_actions": [],
    }
    return report


# ---------------------------------------------------------------------------
# Fixture / analysis-only helpers (F-4S-5)
# ---------------------------------------------------------------------------


def _normalize_fixture_metric(value: Any) -> Optional[int]:
    return _to_int_or_none(value)


def normalize_fixture_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    """fixture/외부 JSON 1건 → unified item dict 정규화."""
    if not isinstance(raw, dict):
        return {}
    metrics_raw = raw.get("metrics") or {}
    if not isinstance(metrics_raw, dict):
        metrics_raw = {}
    metrics = {
        "view_count": _normalize_fixture_metric(metrics_raw.get("view_count")),
        "like_count": _normalize_fixture_metric(metrics_raw.get("like_count")),
        "comment_count": _normalize_fixture_metric(metrics_raw.get("comment_count")),
    }
    risk_flags = raw.get("risk_flags") or []
    if not isinstance(risk_flags, list):
        risk_flags = []
    title = _strip_html(raw.get("title"))
    summary = _strip_html(raw.get("summary"), max_len=300)
    return {
        "platform": _ensure_str(raw.get("platform")),
        "source_type": _ensure_str(raw.get("source_type")),
        "keyword": _ensure_str(raw.get("keyword")),
        "title": title,
        "url": _ensure_str(raw.get("url")),
        "summary": summary,
        "published_at": (_ensure_str(raw.get("published_at")) or None) if raw.get("published_at") else None,
        "channel_or_author": (_ensure_str(raw.get("channel_or_author")) or None)
        if raw.get("channel_or_author")
        else None,
        "metrics": metrics,
        "raw_rank": _to_int_or_none(raw.get("raw_rank")) or 0,
        "risk_flags": [str(x) for x in risk_flags],
    }


def load_fixture_items(path: Path) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """fixture json 파일을 로드 → (items, keywords, warnings).

    fixture json 구조:
    {
      "keywords": ["..."],
      "items": [ ...unified-ish dicts... ]
    }
    """
    text = Path(path).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("fixture root must be an object")
    raw_items = payload.get("items") or []
    if not isinstance(raw_items, list):
        raise ValueError("fixture.items must be a list")
    items: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for idx, raw in enumerate(raw_items):
        norm = normalize_fixture_item(raw)
        if not norm.get("title") and not norm.get("url"):
            warnings.append(f"fixture:item[{idx}]:empty")
        items.append(norm)
    raw_kw = payload.get("keywords") or []
    if not isinstance(raw_kw, list):
        raw_kw = []
    keywords = normalize_keywords(raw_kw)
    return items, keywords, warnings


def build_report_from_items(
    items: Sequence[Dict[str, Any]],
    keywords: Sequence[str],
    *,
    mode: str = "fixture",
    platforms_attempted: Optional[Sequence[str]] = None,
    platforms_live: Optional[Sequence[str]] = None,
    extra_warnings: Optional[Sequence[str]] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """unified item dict 리스트로부터 직접 리포트 생성. 수집 호출 없음."""
    item_dicts: List[Dict[str, Any]] = [normalize_fixture_item(it) if isinstance(it, dict) else {} for it in items]
    item_dicts = [it for it in item_dicts if it]
    summary = summarize_unified_items(
        [
            UnifiedItem(
                platform=it.get("platform", ""),
                source_type=it.get("source_type", ""),
                keyword=it.get("keyword", ""),
                title=it.get("title", ""),
                url=it.get("url", ""),
                summary=it.get("summary", ""),
                published_at=it.get("published_at"),
                channel_or_author=it.get("channel_or_author"),
                metrics=dict(it.get("metrics") or {}),
                raw_rank=int(it.get("raw_rank") or 0),
                risk_flags=list(it.get("risk_flags") or []),
            )
            for it in item_dicts
        ]
    )
    title_terms = extract_title_terms(
        [
            UnifiedItem(
                platform=it.get("platform", ""),
                source_type=it.get("source_type", ""),
                keyword=it.get("keyword", ""),
                title=it.get("title", ""),
                url=it.get("url", ""),
                summary=it.get("summary", ""),
                published_at=it.get("published_at"),
                channel_or_author=it.get("channel_or_author"),
                metrics=dict(it.get("metrics") or {}),
                raw_rank=int(it.get("raw_rank") or 0),
                risk_flags=list(it.get("risk_flags") or []),
            )
            for it in item_dicts
        ],
        top_n=20,
    )
    ideas = build_content_ideas(
        [
            UnifiedItem(
                platform=it.get("platform", ""),
                source_type=it.get("source_type", ""),
                keyword=it.get("keyword", ""),
                title=it.get("title", ""),
                url=it.get("url", ""),
                summary=it.get("summary", ""),
                published_at=it.get("published_at"),
                channel_or_author=it.get("channel_or_author"),
                metrics=dict(it.get("metrics") or {}),
                raw_rank=int(it.get("raw_rank") or 0),
                risk_flags=list(it.get("risk_flags") or []),
            )
            for it in item_dicts
        ],
        keywords,
    )
    ranked_yt = rank_youtube_candidates(item_dicts, keywords, top_n=10)
    ranked_naver = rank_naver_candidates(item_dicts, keywords, top_n=10, by_source_type=True)
    patterns = detect_content_patterns(item_dicts)
    strategy = build_platform_strategy(
        {**summary, "keywords_count": len(list(keywords))},
        ranked_items={"youtube": ranked_yt, "naver": ranked_naver},
        patterns=patterns,
    )
    ltx_briefs = build_ltx_video_briefs(item_dicts, keywords, max_count=5)

    warnings = list(extra_warnings or [])
    platforms_attempted = list(platforms_attempted or sorted({it.get("platform", "") for it in item_dicts if it.get("platform")}))
    platforms_live = list(platforms_live or [])

    return {
        "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "keywords": list(keywords),
        "platforms_attempted": platforms_attempted,
        "platforms_live": platforms_live,
        "summary": {
            **summary,
            "keywords_count": len(list(keywords)),
            "platforms_attempted": platforms_attempted,
            "platforms_live": platforms_live,
            "warnings_count": len(warnings),
            "mode": mode,
        },
        "items": item_dicts,
        "title_terms": [list(pair) for pair in title_terms],
        "content_ideas": ideas,
        "analysis": {
            "ranked_youtube": ranked_yt,
            "ranked_naver": ranked_naver,
            "patterns": patterns,
            "platform_strategy": strategy,
        },
        "ltx_video_briefs": ltx_briefs,
        "warnings": warnings,
        "next_actions": [],
    }


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------


CSV_COLUMNS: Tuple[str, ...] = (
    "platform",
    "source_type",
    "keyword",
    "title",
    "url",
    "summary",
    "published_at",
    "channel_or_author",
    "view_count",
    "like_count",
    "comment_count",
    "risk_flags",
)


def _flatten_for_csv(item: Dict[str, Any]) -> Dict[str, Any]:
    metrics = item.get("metrics") or {}
    risk_flags = item.get("risk_flags") or []
    return {
        "platform": item.get("platform", ""),
        "source_type": item.get("source_type", ""),
        "keyword": item.get("keyword", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "summary": item.get("summary", ""),
        "published_at": item.get("published_at") or "",
        "channel_or_author": item.get("channel_or_author") or "",
        "view_count": "" if metrics.get("view_count") is None else metrics.get("view_count"),
        "like_count": "" if metrics.get("like_count") is None else metrics.get("like_count"),
        "comment_count": "" if metrics.get("comment_count") is None else metrics.get("comment_count"),
        "risk_flags": ";".join(str(x) for x in risk_flags),
    }


def write_report_files(
    report: Dict[str, Any],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Path]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"content_research_{ts}"

    json_path = out_path / f"{base}.json"
    csv_path = out_path / f"{base}.csv"
    md_path = out_path / f"{base}.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for item in report.get("items") or []:
            writer.writerow(_flatten_for_csv(item))

    md_path.write_text(render_markdown_report(report), encoding="utf-8")

    return {"json": json_path, "csv": csv_path, "md": md_path}
