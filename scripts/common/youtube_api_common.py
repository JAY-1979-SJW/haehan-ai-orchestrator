"""Shared constants, path definitions, and utility helpers for research module."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root
from scripts.common.youtube_http_client import (
    api_key as _resolve_api_key,
)
from scripts.common.youtube_http_client import (
    get_json as _http_get_json,
)
from scripts.common.youtube_http_client import (
    get_text as _http_get_text,
)
from scripts.common.youtube_http_client import (
    oauth_token as _resolve_oauth_token,
)

ROOT = repo_root()
REPORT_DIR = ROOT / "data" / "youtube_research_reports"
LATEST_SEARCH = ROOT / "data" / "youtube_research_search_latest.json"
LATEST_TRANSCRIPT_PLAN = ROOT / "data" / "youtube_transcript_plan_latest.json"
LATEST_ANALYSIS = ROOT / "data" / "youtube_transcript_analysis_latest.json"
LATEST_CAPTION_LIST = ROOT / "data" / "youtube_caption_list_latest.json"
LATEST_CAPTION_DOWNLOAD = ROOT / "data" / "youtube_caption_download_latest.json"
LATEST_SCRIPT_COLLECT = ROOT / "data" / "youtube_script_collect_latest.json"
LATEST_VIDEO_SUMMARY = ROOT / "data" / "youtube_video_summary_latest.json"
LATEST_FULL_TRANSCRIPT_STORE = ROOT / "data" / "youtube_full_transcript_store_latest.json"

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
YOUTUBE_CAPTIONS_URL = "https://www.googleapis.com/youtube/v3/captions"
CAPTION_DOWNLOAD_FORMATS = {"srt", "vtt", "ttml"}
YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TRANSCRIPT_SOURCE_POLICY = {
    "allowed": [
        "user_provided_transcript_file",
        "owned_channel_caption_file_obtained_with_oauth",
        "manually_exported_caption_file",
    ],
    "blocked": [
        "unofficial_caption_scraping",
        "browser_hidden_caption_endpoint_scraping",
        "third_party_transcript_api_without_user_approval",
    ],
}
SENSITIVE_WORDS = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|cookie|credential|otp|password|refresh[_-]?token|secret|session[_-]?id|token)"
)
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
    "영상",
    "그리고",
    "그러면",
    "합니다",
    "있는",
    "이번",
    "오늘",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_report(payload: dict[str, Any], latest: Path, prefix: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{prefix}_{_stamp()}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return path


def _api_key(explicit: str | None = None) -> str:
    return _resolve_api_key(explicit)


def _resolve_repo_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved


def _oauth_token(explicit: str | None = None, token_file: str | Path | None = None) -> str:
    return _resolve_oauth_token(explicit, token_file)


def parse_kv_args(args: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    positional: list[str] = []
    for item in args:
        if "=" in item:
            key, value = item.split("=", 1)
            values[key.strip().lstrip("-")] = value.strip()
        elif item.startswith("--"):
            values[item[2:]] = "1"
        else:
            positional.append(item)
    if positional and "query" not in values:
        values["query"] = " ".join(positional)
    return values


def parse_youtube_video_id(value: str) -> str:
    """Extract a YouTube video id from a known URL form or a raw id."""
    raw = (value or "").strip()
    if YOUTUBE_VIDEO_ID_RE.fullmatch(raw):
        return raw
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        return ""
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if host.endswith("youtu.be") and path_parts and YOUTUBE_VIDEO_ID_RE.fullmatch(path_parts[0]):
        return path_parts[0]
    if "youtube.com" not in host:
        return ""
    query_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
    if YOUTUBE_VIDEO_ID_RE.fullmatch(query_id):
        return query_id
    if (
        len(path_parts) >= 2
        and path_parts[0] in {"shorts", "embed", "live"}
        and YOUTUBE_VIDEO_ID_RE.fullmatch(path_parts[1])
    ):
        return path_parts[1]
    return ""


def _get_json(url: str, params: dict[str, str | int]) -> dict[str, Any]:
    return _http_get_json(url, params)


def _get_json_oauth(url: str, params: dict[str, str | int], token: str) -> dict[str, Any]:
    return _http_get_json(url, params, token=token)


def _get_text_oauth(url: str, params: dict[str, str | int], token: str) -> str:
    return _http_get_text(url, params, token=token)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bounded(value: float, *, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))  # noqa: RUF046


def _int_value(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    try:
        return int(float(text))
    except ValueError:
        return 0


def _top_keywords(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    words = [word for word in words if word not in STOPWORDS and len(word) > 1]
    return [{"keyword": word, "count": count} for word, count in Counter(words).most_common(limit)]


def _sentences(text: str) -> list[str]:
    import re as _re

    chunks = _re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 20]


def _read_transcript(path: str | Path) -> str:
    transcript_path = _resolve_repo_path(path)
    text = transcript_path.read_text(encoding="utf-8", errors="replace")
    return SENSITIVE_WORDS.sub("[redacted-sensitive]", text)
