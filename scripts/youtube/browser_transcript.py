"""User-present YouTube visible transcript reader.

This module reads only transcript text that is visible in the user's browser.
It does not call hidden YouTube caption endpoints, unofficial transcript APIs,
or store a full third-party transcript. The output is a derived summary report.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from security_utils import safe_preview

from .research import parse_youtube_video_id


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "youtube_research_reports"
LATEST_BROWSER_TRANSCRIPT_SUMMARY = ROOT / "data" / "youtube_browser_transcript_summary_latest.json"
WORD_RE = re.compile(r"[A-Za-z가-힣0-9][A-Za-z가-힣0-9_+-]{1,}")
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
    "이제",
    "오늘",
    "정말",
}

OPEN_TRANSCRIPT_JS = r"""() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const texts = ['Show transcript', 'Transcript', '스크립트 표시', '스크립트', '자막 스크립트', '대본'];
  const candidates = Array.from(document.querySelectorAll('button, ytd-button-renderer, tp-yt-paper-item, yt-button-shape button'));
  for (const el of candidates) {
    const text = (el.innerText || el.textContent || '').trim();
    const aria = (el.getAttribute('aria-label') || '').trim();
    if (!visible(el)) continue;
    if (texts.some(t => text.includes(t) || aria.includes(t))) {
      el.click();
      return {clicked: true, label: text || aria};
    }
  }
  const more = candidates.find(el => {
    const text = (el.innerText || el.textContent || '').trim();
    const aria = (el.getAttribute('aria-label') || '').trim();
    return visible(el) && ['More', '더보기', '...'].some(t => text.includes(t) || aria.includes(t));
  });
  if (more) {
    more.click();
    return {clicked: true, label: (more.innerText || more.getAttribute('aria-label') || '').trim(), needs_retry: true};
  }
  return {clicked: false, label: ''};
}"""

EXTRACT_VISIBLE_TRANSCRIPT_JS = r"""() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const selectors = [
    'ytd-transcript-segment-renderer',
    'yt-formatted-string.segment-text',
    '#segments-container yt-formatted-string',
    'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]'
  ];
  const rows = [];
  for (const sel of selectors) {
    for (const el of Array.from(document.querySelectorAll(sel))) {
      if (!visible(el)) continue;
      const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
      if (text && text.length >= 2) rows.push(text);
    }
  }
  const seen = new Set();
  return rows.filter(text => {
    const key = text.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 500);
}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_report(payload: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"youtube_browser_transcript_summary_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LATEST_BROWSER_TRANSCRIPT_SUMMARY.write_text(text, encoding="utf-8")
    return path


def _top_keywords(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    words = [word for word in words if word not in STOPWORDS and len(word) > 1]
    return [{"keyword": word, "count": count} for word, count in Counter(words).most_common(limit)]


def summarize_visible_segments(
    segments: list[str],
    *,
    video_id: str = "",
    url: str = "",
    max_highlights: int = 12,
) -> dict[str, Any]:
    """Create a derived summary without returning the full transcript."""
    clean_segments = [re.sub(r"\s+", " ", item).strip() for item in segments if item and item.strip()]
    text = " ".join(clean_segments)
    keywords = _top_keywords(text)
    highlights = [
        safe_preview(item, limit=180)
        for item in clean_segments
        if len(item) >= 20 and not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", item)
    ][:max_highlights]
    return {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_browser_visible_transcript_summary",
        "ok": bool(clean_segments),
        "status": "ok" if clean_segments else "blocked",
        "reason": "" if clean_segments else "visible_transcript_not_found",
        "video_id": safe_preview(video_id, limit=80),
        "video_url": url or (f"https://www.youtube.com/watch?v={video_id}" if video_id else ""),
        "state_change": False,
        "secret_values_read": False,
        "source_policy": "browser_visible_transcript_only_user_present",
        "raw_transcript_stored": False,
        "segment_count_observed": len(clean_segments),
        "word_like_count": len(WORD_RE.findall(text)),
        "top_keywords": keywords,
        "derived_summary": {
            "method": "local_extract_from_visible_transcript",
            "topics": [row["keyword"] for row in keywords[:8]],
            "highlights": highlights,
        },
        "blocked_sources": [
            "unofficial_caption_scraping",
            "browser_hidden_caption_endpoint_scraping",
            "third_party_transcript_api_without_user_approval",
        ],
        "copyright_note": "Full third-party transcript is not stored or printed; use this derived summary for review.",
    }


def collect_visible_transcript_summary(
    url_or_video_id: str,
    *,
    max_segments: int = 160,
    wait_seconds: float = 4.0,
    open_transcript: bool = True,
) -> tuple[dict[str, Any], Path]:
    """Open a YouTube URL in the local user browser and summarize visible transcript text."""
    video_id = parse_youtube_video_id(url_or_video_id)
    if not video_id:
        payload = summarize_visible_segments([], video_id="", url="")
        payload["reason"] = "invalid_youtube_video_url_or_id"
        payload["input"] = safe_preview(url_or_video_id, limit=180)
        return payload, _write_report(payload)

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        from scripts.web_connector import open_page

        page = open_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(int(max(0.5, wait_seconds) * 1000))
        open_result: dict[str, Any] = {"clicked": False, "label": ""}
        if open_transcript:
            open_result = page.evaluate(OPEN_TRANSCRIPT_JS) or {"clicked": False, "label": ""}
            page.wait_for_timeout(1200)
            if open_result.get("needs_retry"):
                open_result = page.evaluate(OPEN_TRANSCRIPT_JS) or open_result
                page.wait_for_timeout(1200)
        segments = page.evaluate(EXTRACT_VISIBLE_TRANSCRIPT_JS) or []
    except Exception as exc:
        payload = summarize_visible_segments([], video_id=video_id, url=url)
        payload.update(
            {
                "status": "blocked",
                "ok": False,
                "reason": "browser_visible_transcript_executor_unavailable",
                "error_type": type(exc).__name__,
                "error_summary": safe_preview(str(exc), limit=240),
                "next_step": "Start local CDP Chrome, open the video, show the transcript panel, then rerun this executor.",
            }
        )
        return payload, _write_report(payload)

    payload = summarize_visible_segments(list(segments)[:max_segments], video_id=video_id, url=url)
    payload["browser_action"] = {
        "opened_video_url": True,
        "open_transcript_attempted": open_transcript,
        "open_transcript_result": {
            "clicked": bool(open_result.get("clicked")),
            "label": safe_preview(str(open_result.get("label") or ""), limit=120),
        },
    }
    if payload["status"] != "ok":
        payload["next_step"] = "Open the visible YouTube transcript panel manually, then rerun this executor."
    return payload, _write_report(payload)


__all__ = [
    "collect_visible_transcript_summary",
    "summarize_visible_segments",
]
