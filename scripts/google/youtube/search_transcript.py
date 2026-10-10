"""Visible transcript panel extraction via CDP browser session."""

from __future__ import annotations

import re
from typing import Any

from scripts.browser.cdp.cdp_console import connect
from scripts.google.youtube.search_common import WORD_RE, _top_keywords
from ai_orchestrator.core.security_utils import safe_preview


def collect_visible_transcript_summary(
    video_id: str,
    *,
    wait_seconds: float = 3.0,
    max_segments: int = 180,
) -> dict[str, Any]:
    """Open a video and summarize visible transcript text via CDP.

    This uses visible page controls only. It does not call timedtext, captions,
    or other hidden transcript endpoints.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    base = {
        "status": "blocked",
        "reason": "",
        "video_id": safe_preview(video_id, limit=20),
        "url": url,
        "raw_transcript_stored": False,
        "hidden_endpoint_scraping": False,
        "segments_observed": 0,
        "word_like_count": 0,
        "top_keywords": [],
        "highlights": [],
    }
    try:
        with connect() as session:
            session.goto(url, wait_idle=False)
            session.wait(wait_seconds)
            opened = _try_open_transcript_panel(session)
            if opened.get("needs_wait"):
                session.wait(1.5)
            segments = _extract_visible_transcript_segments(session, limit=max_segments)
    except Exception as exc:  # noqa: BLE001 - YouTube 자막 CDP 추출 실패 시 reason=youtube_transcript_cdp_unavailable 과 에러 요약을 담아 반환 - 읽기전용 자막 조회, 실패를 명시적으로 표시할 뿐 위험 조작 없음
        base["reason"] = "youtube_transcript_cdp_unavailable"
        base["error"] = safe_preview(str(exc), limit=220)
        return base

    if not segments:
        base["reason"] = "visible_transcript_not_found"
        base["open_transcript_result"] = opened
        return base

    summary = summarize_transcript_segments(segments)
    base.update(summary)
    base["status"] = "ok"
    base["reason"] = ""
    base["open_transcript_result"] = opened
    return base


def _try_open_transcript_panel(session: Any) -> dict[str, Any]:
    data, err = session.js_json(
        r"""(function() {
            function visible(el) {
                if (!el) return false;
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }
            var labels = ['Show transcript', 'Transcript', '스크립트 표시', '스크립트', '자막 스크립트', '대본'];
            var controls = Array.from(document.querySelectorAll('button, ytd-button-renderer, tp-yt-paper-item, yt-button-shape button'));
            for (var i = 0; i < controls.length; i++) {
                var el = controls[i];
                if (!visible(el)) continue;
                var text = ((el.innerText || el.textContent || '') + '').trim();
                var aria = ((el.getAttribute('aria-label') || '') + '').trim();
                for (var j = 0; j < labels.length; j++) {
                    if (text.indexOf(labels[j]) >= 0 || aria.indexOf(labels[j]) >= 0) {
                        el.click();
                        return {clicked: true, label: (text || aria).slice(0, 80), needs_wait: true};
                    }
                }
            }
            return {clicked: false, label: '', needs_wait: false};
        })()"""
    )
    if err or not isinstance(data, dict):
        return {"clicked": False, "label": "", "needs_wait": False, "error": safe_preview(str(data), limit=120)}
    return {
        "clicked": bool(data.get("clicked")),
        "label": safe_preview(data.get("label", ""), limit=80),
        "needs_wait": bool(data.get("needs_wait")),
    }


def _extract_visible_transcript_segments(session: Any, *, limit: int = 180) -> list[str]:
    data, err = session.js_json(
        f"""(function() {{
            function visible(el) {{
                if (!el) return false;
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }}
            var selectors = [
                'ytd-transcript-segment-renderer',
                'yt-formatted-string.segment-text',
                '#segments-container yt-formatted-string',
                'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]'
            ];
            var rows = [];
            for (var s = 0; s < selectors.length; s++) {{
                var nodes = Array.from(document.querySelectorAll(selectors[s]));
                for (var i = 0; i < nodes.length; i++) {{
                    var el = nodes[i];
                    if (!visible(el)) continue;
                    var text = ((el.innerText || el.textContent || '') + '').replace(/\\s+/g, ' ').trim();
                    if (text && text.length >= 2) rows.push(text);
                }}
            }}
            var seen = {{}};
            return rows.filter(function(text) {{
                var key = text.toLowerCase();
                if (seen[key]) return false;
                seen[key] = true;
                return true;
            }}).slice(0, {limit});
        }})()"""
    )
    if err or not isinstance(data, list):
        return []
    return [safe_preview(item, limit=240) for item in data if str(item).strip()]


def summarize_transcript_segments(segments: list[str]) -> dict[str, Any]:
    clean_segments = [re.sub(r"\s+", " ", str(item)).strip() for item in segments if str(item).strip()]
    text = " ".join(clean_segments)
    keywords = _top_keywords(text)
    highlights = [
        safe_preview(segment, limit=180)
        for segment in clean_segments
        if len(segment) >= 20 and not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", segment)
    ][:10]
    return {
        "segments_observed": len(clean_segments),
        "word_like_count": len(WORD_RE.findall(text)),
        "top_keywords": keywords,
        "highlights": highlights,
        "topics": [item["keyword"] for item in keywords[:8]],
    }
