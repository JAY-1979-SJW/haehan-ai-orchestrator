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
        "items": [it.to_dict() for it in items],
        "title_terms": [list(pair) for pair in title_terms],
        "content_ideas": ideas,
        "warnings": warnings,
        "next_actions": [],
    }
    return report


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
