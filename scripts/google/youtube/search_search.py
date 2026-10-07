"""Official API and browser DOM search collectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.browser.cdp.cdp_console import connect
from scripts.google.youtube.search_common import (
    LATEST_SEARCH,
    ROOT,
    YOUTUBE_SEARCH_URL,
    YOUTUBE_VIDEOS_URL,
    _api_key,
    _base_payload,
    _get_json,
    _oauth_access_token,
    _search_cache_get,
    _search_cache_key,
    _search_cache_set,
    _write_report,
    build_search_url,
)
from ai_orchestrator.core.security_utils import safe_preview


def search_videos(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    query: str,
    *,
    max_results: int = 10,
    source: str = "auto",
    api_key: str | None = None,
    wait_seconds: float = 3.0,
    order: str = "relevance",
    published_after: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Collect YouTube video search results.

    source values:
    - official: official YouTube Data API only.
    - browser: public search results page DOM only.
    - auto: official API when an API key is available, otherwise browser DOM.

    order: "relevance" (기본) 또는 "date"(최신 등록일순). API 비용(unit)은
    정렬 방식과 무관하게 동일하다 — 정렬을 바꿔도 일일 검색 한도는 늘지 않는다.
    published_after: ISO 8601 UTC 문자열(예: "2026-08-01T00:00:00Z"). 이 시각
    이후 등록된 영상만 반환한다. browser 소스는 지원하지 않는다.
    """
    normalized_source = (source or "auto").strip().lower()
    if normalized_source not in {"auto", "official", "browser"}:
        payload = _base_payload(query, normalized_source, max_results)
        payload.update({"ok": False, "status": "blocked", "reason": "unknown_youtube_search_source"})
        return _write_report(payload)

    key = _api_key(api_key)
    has_oauth = bool(_oauth_access_token())
    if normalized_source == "official" or (normalized_source == "auto" and (key or has_oauth)):
        if not key and not has_oauth:
            payload = _base_payload(query, "official", max_results)
            payload.update(
                {
                    "ok": False,
                    "status": "blocked",
                    "reason": "youtube_data_api_key_required_for_official_source",
                    "next_step": "Set YOUTUBE_DATA_API_KEY or complete OAuth flow.",
                }
            )
            return _write_report(payload)
        return search_videos_official(
            query, max_results=max_results, api_key=key, order=order, published_after=published_after
        )

    return search_videos_browser(query, max_results=max_results, wait_seconds=wait_seconds)


def search_videos_official(
    query: str,
    *,
    max_results: int = 10,
    api_key: str | None = None,
    order: str = "relevance",
    published_after: str | None = None,
) -> tuple[dict[str, Any], Path]:
    key = _api_key(api_key)
    max_results = max(1, min(int(max_results), 25))
    order = order if order in {"relevance", "date"} else "relevance"
    payload = _base_payload(query, "official", max_results)
    payload["order"] = order
    payload["published_after"] = published_after or ""
    if not key and not _oauth_access_token():
        payload.update(
            {
                "ok": False,
                "status": "blocked",
                "reason": "youtube_data_api_key_required_for_official_source",
                "next_step": "Set YOUTUBE_DATA_API_KEY or complete OAuth flow.",
            }
        )
        return _write_report(payload)

    # 캐시 조회 (Search Queries per day 쿼터 100회/일 절약)
    # order/published_after 가 다르면 결과가 달라지므로 캐시 키에 포함한다.
    cache_key = _search_cache_key(f"{query}|{order}|{published_after or ''}", max_results)
    cached = _search_cache_get(cache_key)
    if cached:
        cached["cache_hit"] = True
        return _write_report(cached)

    # API 키가 있으면 key 파라미터, OAuth면 _get_json이 Authorization 헤더 자동 추가
    params: dict[str, str | int] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "safeSearch": "moderate",
        "order": order,
    }
    if published_after:
        params["publishedAfter"] = published_after
    if key:
        params["key"] = key

    try:
        search_data = _get_json(YOUTUBE_SEARCH_URL, params)
    except Exception as exc:  # noqa: BLE001 - 유튜브 검색 API/브라우저 폴백 조회 — API 호출 실패 시 payload에 status=blocked 로 명시적 기록 후 반환, 상세정보 조회 실패는 빈 목록으로 폴백할 뿐 쓰기 없음
        payload.update(
            {
                "ok": False,
                "status": "blocked",
                "reason": "youtube_data_api_request_failed",
                "error": safe_preview(str(exc), limit=240),
                "results": [],
            }
        )
        return _write_report(payload)
    video_ids = [
        item.get("id", {}).get("videoId", "")
        for item in search_data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    details: dict[str, Any] = {"items": []}
    if video_ids:
        try:
            details = _get_json(
                YOUTUBE_VIDEOS_URL,
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(video_ids),
                    "key": key,
                },
            )
        except Exception:  # noqa: BLE001 - 유튜브 검색 API/브라우저 폴백 조회 — API 호출 실패 시 payload에 status=blocked 로 명시적 기록 후 반환, 상세정보 조회 실패는 빈 목록으로 폴백할 뿐 쓰기 없음
            details = {"items": []}
    detail_by_id = {item.get("id"): item for item in details.get("items", [])}
    rows: list[dict[str, Any]] = []
    for item in search_data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        detail = detail_by_id.get(video_id, {})
        rows.append(
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": safe_preview(snippet.get("title", ""), limit=180),
                "channel_title": safe_preview(snippet.get("channelTitle", ""), limit=120),
                "published_at": snippet.get("publishedAt", ""),
                "description": safe_preview(snippet.get("description", ""), limit=500),
                "duration": detail.get("contentDetails", {}).get("duration", ""),
                "caption_available_hint": detail.get("contentDetails", {}).get("caption", ""),
                "statistics": {
                    "view_count": detail.get("statistics", {}).get("viewCount", ""),
                    "like_count": detail.get("statistics", {}).get("likeCount", ""),
                    "comment_count": detail.get("statistics", {}).get("commentCount", ""),
                },
                "collection_source": "official_youtube_data_api",
            }
        )

    payload.update(
        {
            "ok": True,
            "status": "ok",
            "reason": "",
            "credential_source": "api_key",
            "api_key_output": "redacted",
            "result_count": len(rows),
            "results": rows,
            "cache_hit": False,
        }
    )
    _search_cache_set(cache_key, payload)
    return _write_report(payload)


def search_videos_browser(
    query: str,
    *,
    max_results: int = 10,
    wait_seconds: float = 3.0,
) -> tuple[dict[str, Any], Path]:
    max_results = max(1, min(int(max_results), 25))
    payload = _base_payload(query, "browser", max_results)
    payload["search_url"] = build_search_url(query)
    try:
        with connect() as session:
            session.goto(payload["search_url"], wait_idle=False)
            session.wait(wait_seconds)
            snapshot = extract_browser_search_results(session, limit=max_results)
    except Exception as exc:  # noqa: BLE001 - 유튜브 검색 API/브라우저 폴백 조회 — API 호출 실패 시 payload에 status=blocked 로 명시적 기록 후 반환, 상세정보 조회 실패는 빈 목록으로 폴백할 뿐 쓰기 없음
        payload.update(
            {
                "ok": False,
                "status": "blocked",
                "reason": "youtube_browser_cdp_unavailable",
                "error": safe_preview(str(exc), limit=240),
                "results": [],
            }
        )
        return _write_report(payload)

    if snapshot.get("challenge_detected"):
        payload.update(
            {
                "ok": False,
                "status": "blocked",
                "reason": "youtube_browser_challenge_detected",
                "challenge_markers": snapshot.get("challenge_markers", []),
                "results": [],
            }
        )
        return _write_report(payload)

    payload.update(
        {
            "ok": True,
            "status": "ok",
            "reason": "",
            "final_url": safe_preview(snapshot.get("url", ""), limit=220),
            "title": safe_preview(snapshot.get("title", ""), limit=160),
            "result_count": len(snapshot.get("results", [])),
            "results": snapshot.get("results", []),
            "warnings": snapshot.get("warnings", []),
        }
    )
    return _write_report(payload)


def extract_browser_search_results(session: Any, *, limit: int = 10) -> dict[str, Any]:
    data, err = session.js_json(
        f"""(function() {{
            function clean(value, max) {{
                return ((value || '') + '').replace(/\\s+/g, ' ').trim().slice(0, max);
            }}
            function visible(el) {{
                if (!el) return false;
                var rect = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }}
            function videoIdFromUrl(url) {{
                try {{
                    var parsed = new URL(url, location.href);
                    return parsed.searchParams.get('v') || '';
                }} catch (e) {{
                    return '';
                }}
            }}
            var text = clean(document.body && document.body.innerText, 4000).toLowerCase();
            var challengeMarkers = ['captcha', 'unusual traffic', 'robot', 'verify you are human', 'not a robot']
                .filter(function(marker) {{ return text.indexOf(marker) >= 0; }});
            var nodes = Array.from(document.querySelectorAll('ytd-video-renderer, ytd-grid-video-renderer, ytd-rich-item-renderer, ytd-compact-video-renderer'));
            var seen = {{}};
            var results = [];
            for (var i = 0; i < nodes.length && results.length < {limit}; i++) {{
                var node = nodes[i];
                if (!visible(node)) continue;
                var link = node.querySelector('a#video-title, a#video-title-link, a[href*="/watch?v="]');
                if (!link) continue;
                var href = link.href || link.getAttribute('href') || '';
                var videoId = videoIdFromUrl(href);
                if (!videoId || seen[videoId]) continue;
                seen[videoId] = true;
                var title = clean(link.textContent || link.getAttribute('title') || link.getAttribute('aria-label'), 180);
                var channel = clean((node.querySelector('ytd-channel-name yt-formatted-string, #channel-name yt-formatted-string, a.yt-simple-endpoint[href*="/@"]') || {{}}).textContent, 120);
                var meta = Array.from(node.querySelectorAll('#metadata-line span, ytd-video-meta-block span'))
                    .map(function(el) {{ return clean(el.textContent, 80); }})
                    .filter(Boolean);
                var description = clean((node.querySelector('#description-text, #dismissible #description') || {{}}).textContent, 300);
                var thumbnail = node.querySelector('img');
                results.push({{
                    video_id: videoId,
                    url: 'https://www.youtube.com/watch?v=' + videoId,
                    title: title,
                    channel_title: channel,
                    metadata_line: meta,
                    description: description,
                    thumbnail_present: !!thumbnail,
                    collection_source: 'public_youtube_search_dom'
                }});
            }}
            return {{
                url: location.href,
                title: document.title,
                challenge_detected: challengeMarkers.length > 0,
                challenge_markers: challengeMarkers,
                result_count: results.length,
                results: results,
                warnings: results.length ? [] : ['no_visible_video_results_detected']
            }};
        }})()"""
    )
    if err or not isinstance(data, dict):
        return {
            "url": "",
            "title": "",
            "challenge_detected": False,
            "challenge_markers": [],
            "results": [],
            "warnings": [safe_preview(str(data), limit=200)],
        }
    return _sanitize_browser_snapshot(data)


def _sanitize_browser_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "url": safe_preview(str(data.get("url", "")).split("&pp=", 1)[0], limit=220),
        "title": safe_preview(data.get("title", ""), limit=160),
        "challenge_detected": bool(data.get("challenge_detected")),
        "challenge_markers": [safe_preview(item, limit=80) for item in data.get("challenge_markers", [])],
        "warnings": [safe_preview(item, limit=160) for item in data.get("warnings", [])],
        "results": [],
    }
    for item in data.get("results", []):
        if not isinstance(item, dict):
            continue
        sanitized["results"].append(
            {
                "video_id": safe_preview(item.get("video_id", ""), limit=20),
                "url": safe_preview(item.get("url", ""), limit=120),
                "title": safe_preview(item.get("title", ""), limit=180),
                "channel_title": safe_preview(item.get("channel_title", ""), limit=120),
                "metadata_line": [safe_preview(value, limit=80) for value in item.get("metadata_line", [])[:4]],
                "description": safe_preview(item.get("description", ""), limit=300),
                "thumbnail_present": bool(item.get("thumbnail_present")),
                "collection_source": "public_youtube_search_dom",
            }
        )
    return sanitized


def _load_search_payload(search_report_path: str | Path | None) -> dict[str, Any]:
    import json

    path = Path(search_report_path) if search_report_path else LATEST_SEARCH
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {"results": []}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"results": []}
    return parsed if isinstance(parsed, dict) else {"results": []}
