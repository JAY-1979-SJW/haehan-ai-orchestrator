"""YouTube caption listing, download, transcript storage, and script collection."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from scripts.common.youtube_api_common import (
    CAPTION_DOWNLOAD_FORMATS,
    LATEST_CAPTION_DOWNLOAD,
    LATEST_CAPTION_LIST,
    LATEST_FULL_TRANSCRIPT_STORE,
    LATEST_SCRIPT_COLLECT,
    LATEST_TRANSCRIPT_PLAN,
    REPORT_DIR,
    SENSITIVE_WORDS,
    TRANSCRIPT_SOURCE_POLICY,
    WORD_RE,
    YOUTUBE_CAPTIONS_URL,
    _get_json_oauth,
    _get_text_oauth,
    _now,
    _oauth_token,
    _resolve_repo_path,
    _stamp,
    _write_report,
)
from ai_orchestrator.core.security_utils import safe_preview


def build_transcript_collection_plan(video_id: str, *, owned: bool = False) -> tuple[dict[str, Any], Path]:
    """Create a compliant transcript collection plan for a specific video."""
    video_id = video_id.strip()
    allowed_sources = list(TRANSCRIPT_SOURCE_POLICY["allowed"])
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_transcript_collection_plan",
        "ok": bool(video_id),
        "status": "ready" if video_id else "blocked",
        "video_id": safe_preview(video_id, limit=80),
        "video_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "state_change": False,
        "policy": TRANSCRIPT_SOURCE_POLICY,
        "owned_or_authorized_video": owned,
        "allowed_next_steps": allowed_sources,
        "blocked_next_steps": list(TRANSCRIPT_SOURCE_POLICY["blocked"]),
        "note": (
            "The official YouTube Data API can search videos and inspect metadata. "
            "Caption download requires ownership/OAuth permission or a user-provided transcript file."
        ),
    }
    return payload, _write_report(payload, LATEST_TRANSCRIPT_PLAN, "youtube_transcript_plan")


def list_captions(
    video_id: str,
    *,
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """List authorized caption tracks through the official YouTube Data API."""
    video_id = video_id.strip()
    token = _oauth_token(oauth_token, token_file)
    if not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_list",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_oauth_token_required",
            "video_id": safe_preview(video_id, limit=80),
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Provide an approved owner/authorized OAuth access token or a user-provided transcript file.",
            "captions": [],
        }
        return payload, _write_report(payload, LATEST_CAPTION_LIST, "youtube_caption_list")

    data = _get_json_oauth(
        YOUTUBE_CAPTIONS_URL,
        {"part": "snippet", "videoId": video_id},
        token,
    )
    captions: list[dict[str, Any]] = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        captions.append(
            {
                "caption_id": safe_preview(item.get("id", ""), limit=120),
                "video_id": safe_preview(snippet.get("videoId", video_id), limit=80),
                "language": safe_preview(snippet.get("language", ""), limit=40),
                "name": safe_preview(snippet.get("name", ""), limit=120),
                "track_kind": safe_preview(snippet.get("trackKind", ""), limit=80),
                "audio_track_type": safe_preview(snippet.get("audioTrackType", ""), limit=80),
                "status": safe_preview(snippet.get("status", ""), limit=80),
                "is_draft": bool(snippet.get("isDraft", False)),
                "last_updated": safe_preview(snippet.get("lastUpdated", ""), limit=80),
            }
        )
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_caption_list",
        "ok": True,
        "status": "ok",
        "video_id": safe_preview(video_id, limit=80),
        "state_change": False,
        "secret_values_read": False,
        "oauth_token_output": "redacted",
        "source_policy": "official_youtube_captions_api_authorized_only",
        "caption_count": len(captions),
        "captions": captions,
    }
    return payload, _write_report(payload, LATEST_CAPTION_LIST, "youtube_caption_list")


def download_caption(
    caption_id: str,
    *,
    tfmt: str = "srt",
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
    output: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Download an authorized caption track through the official YouTube Data API."""
    caption_id = caption_id.strip()
    tfmt = (tfmt or "srt").strip().lower()
    if tfmt not in CAPTION_DOWNLOAD_FORMATS:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_download",
            "ok": False,
            "status": "blocked",
            "reason": "unsupported_caption_format",
            "caption_id": safe_preview(caption_id, limit=120),
            "requested_format": safe_preview(tfmt, limit=20),
            "allowed_formats": sorted(CAPTION_DOWNLOAD_FORMATS),
            "state_change": False,
            "secret_values_read": False,
        }
        return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")

    token = _oauth_token(oauth_token, token_file)
    if not token:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_download",
            "ok": False,
            "status": "blocked",
            "reason": "youtube_oauth_token_required",
            "caption_id": safe_preview(caption_id, limit=120),
            "requested_format": tfmt,
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Provide an approved owner/authorized OAuth access token or a user-provided transcript file.",
        }
        return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")

    try:
        text = _get_text_oauth(f"{YOUTUBE_CAPTIONS_URL}/{urllib.parse.quote(caption_id)}", {"tfmt": tfmt}, token)
    except Exception as exc:  # noqa: BLE001 - 자막 다운로드(oauth) 실패 시 ok=False, status=blocked 인 실패 payload를 반환하는 fail-closed 경로.
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_caption_download",
            "ok": False,
            "status": "blocked",
            "reason": "official_caption_download_forbidden_or_unavailable",
            "error_type": type(exc).__name__,
            "error_summary": safe_preview(str(exc), limit=200),
            "caption_id": safe_preview(caption_id, limit=120),
            "requested_format": tfmt,
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Use an owned/authorized video with downloadable captions, or provide a user-exported transcript file.",
        }
        return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")
    sanitized = SENSITIVE_WORDS.sub("[redacted-sensitive]", text)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    transcript_path = (
        _resolve_repo_path(output) if output else REPORT_DIR / f"youtube_caption_download_{_stamp()}.{tfmt}"
    )
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(sanitized, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_caption_download",
        "ok": True,
        "status": "ok",
        "caption_id": safe_preview(caption_id, limit=120),
        "requested_format": tfmt,
        "state_change": False,
        "secret_values_read": False,
        "oauth_token_output": "redacted",
        "source_policy": "official_youtube_captions_api_authorized_only",
        "transcript_path": str(transcript_path),
        "character_count": len(sanitized),
        "word_like_count": len(WORD_RE.findall(sanitized)),
    }
    return payload, _write_report(payload, LATEST_CAPTION_DOWNLOAD, "youtube_caption_download")


def store_full_transcript_file(
    transcript_file: str | Path,
    *,
    video_id: str = "",
    title: str = "",
    rights_confirmed: bool = False,
    source_type: str = "user_provided_or_licensed",
    output: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Store a full transcript only when the user confirms rights/authorization."""
    if not rights_confirmed:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_full_transcript_store",
            "ok": False,
            "status": "blocked",
            "reason": "rights_confirmation_required",
            "video_id": safe_preview(video_id, limit=80),
            "title": safe_preview(title, limit=180),
            "state_change": False,
            "full_transcript_stored": False,
            "allowed_sources": [
                "user_provided_transcript_file",
                "owned_or_licensed_transcript_file",
                "official_caption_download_with_authorized_oauth",
            ],
            "blocked_sources": [
                "third_party_browser_visible_transcript_full_text_storage",
                "hidden_caption_endpoint_scraping",
                "unofficial_transcript_api_without_approval",
            ],
            "next_step": "Rerun with rights_confirmed=1 only for owned, licensed, or user-provided transcript text.",
        }
        return payload, _write_report(payload, LATEST_FULL_TRANSCRIPT_STORE, "youtube_full_transcript_store")

    source = _resolve_repo_path(transcript_file)
    if not source.exists() or not source.is_file():
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_full_transcript_store",
            "ok": False,
            "status": "blocked",
            "reason": "transcript_file_not_found",
            "input": safe_preview(str(transcript_file), limit=180),
            "state_change": False,
            "full_transcript_stored": False,
        }
        return payload, _write_report(payload, LATEST_FULL_TRANSCRIPT_STORE, "youtube_full_transcript_store")

    text = SENSITIVE_WORDS.sub("[redacted-sensitive]", source.read_text(encoding="utf-8", errors="replace"))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix if source.suffix else ".txt"
    target = _resolve_repo_path(output) if output else REPORT_DIR / f"youtube_full_transcript_{_stamp()}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_full_transcript_store",
        "ok": True,
        "status": "ok",
        "video_id": safe_preview(video_id, limit=80),
        "title": safe_preview(title, limit=180),
        "state_change": False,
        "source_type": safe_preview(source_type, limit=80),
        "rights_confirmed": True,
        "secret_values_read": False,
        "full_transcript_stored": True,
        "raw_transcript_path": str(target),
        "character_count": len(text),
        "word_like_count": len(WORD_RE.findall(text)),
        "policy": "owned_licensed_or_user_provided_full_text_only",
        "copyright_note": "Store and reuse only when you have rights or authorization for this transcript.",
    }
    return payload, _write_report(payload, LATEST_FULL_TRANSCRIPT_STORE, "youtube_full_transcript_store")


def collect_script_from_url(
    url_or_video_id: str,
    *,
    tfmt: str = "srt",
    oauth_token: str | None = None,
    token_file: str | Path | None = None,
    analyze: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Collect a transcript from a YouTube URL through approved sources only."""
    from scripts.youtube.research_analysis import analyze_transcript
    from scripts.common.youtube_api_common import parse_youtube_video_id

    video_id = parse_youtube_video_id(url_or_video_id)
    if not video_id:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_script_collect",
            "ok": False,
            "status": "blocked",
            "reason": "invalid_youtube_video_url_or_id",
            "input": safe_preview(url_or_video_id, limit=180),
            "state_change": False,
            "secret_values_read": False,
            "source_policy": "official_youtube_captions_api_authorized_only",
            "next_step": "Provide a YouTube watch, youtu.be, shorts, embed URL, or an 11-character video id.",
        }
        return payload, _write_report(payload, LATEST_SCRIPT_COLLECT, "youtube_script_collect")

    plan, plan_path = build_transcript_collection_plan(video_id)
    caption_list, caption_list_path = list_captions(video_id, oauth_token=oauth_token, token_file=token_file)
    if caption_list.get("status") != "ok":
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_script_collect",
            "ok": False,
            "status": "blocked",
            "reason": caption_list.get("reason") or "caption_list_unavailable",
            "video_id": safe_preview(video_id, limit=80),
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "plan_report": str(plan_path),
            "caption_list_report": str(caption_list_path),
            "allowed_next_steps": plan["allowed_next_steps"],
            "blocked_next_steps": plan["blocked_next_steps"],
            "next_step": caption_list.get("next_step")
            or "Provide approved OAuth credentials or a user-exported transcript file.",
        }
        return payload, _write_report(payload, LATEST_SCRIPT_COLLECT, "youtube_script_collect")

    captions = caption_list.get("captions", [])
    if not captions:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_script_collect",
            "ok": False,
            "status": "blocked",
            "reason": "caption_track_not_found",
            "video_id": safe_preview(video_id, limit=80),
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "plan_report": str(plan_path),
            "caption_list_report": str(caption_list_path),
            "caption_count": 0,
            "allowed_next_steps": plan["allowed_next_steps"],
            "blocked_next_steps": plan["blocked_next_steps"],
            "next_step": "Use a video with authorized captions, or provide a user-exported browser-visible transcript file.",
        }
        return payload, _write_report(payload, LATEST_SCRIPT_COLLECT, "youtube_script_collect")

    selected = captions[0]
    download, download_path = download_caption(
        selected["caption_id"],
        tfmt=tfmt,
        oauth_token=oauth_token,
        token_file=token_file,
    )
    if download.get("status") != "ok":
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_script_collect",
            "ok": False,
            "status": "blocked",
            "reason": download.get("reason") or "caption_download_unavailable",
            "video_id": safe_preview(video_id, limit=80),
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "state_change": False,
            "secret_values_read": False,
            "oauth_token_output": "redacted",
            "source_policy": "official_youtube_captions_api_authorized_only",
            "plan_report": str(plan_path),
            "caption_list_report": str(caption_list_path),
            "caption_download_report": str(download_path),
            "caption_count": caption_list.get("caption_count", len(captions)),
            "selected_caption": selected,
            "allowed_next_steps": plan["allowed_next_steps"],
            "blocked_next_steps": plan["blocked_next_steps"],
            "next_step": download.get("next_step")
            or "Use an owned/authorized video with downloadable captions, or provide a user-exported transcript file.",
        }
        return payload, _write_report(payload, LATEST_SCRIPT_COLLECT, "youtube_script_collect")

    analysis_path = ""
    analysis_status = "skipped"
    if analyze:
        analysis, analysis_report_path = analyze_transcript(download["transcript_path"], video_id=video_id)
        analysis_status = analysis.get("status", "unknown")
        analysis_path = str(analysis_report_path)

    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_script_collect",
        "ok": True,
        "status": "ok",
        "video_id": safe_preview(video_id, limit=80),
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "state_change": False,
        "secret_values_read": False,
        "oauth_token_output": "redacted",
        "source_policy": "official_youtube_captions_api_authorized_only",
        "plan_report": str(plan_path),
        "caption_list_report": str(caption_list_path),
        "caption_download_report": str(download_path),
        "caption_count": caption_list.get("caption_count", len(captions)),
        "selected_caption": selected,
        "transcript_path": download["transcript_path"],
        "character_count": download.get("character_count", 0),
        "word_like_count": download.get("word_like_count", 0),
        "analysis_status": analysis_status,
        "analysis_report": analysis_path,
        "copyright_note": "Do not publish copied transcript text without rights review.",
    }
    return payload, _write_report(payload, LATEST_SCRIPT_COLLECT, "youtube_script_collect")
