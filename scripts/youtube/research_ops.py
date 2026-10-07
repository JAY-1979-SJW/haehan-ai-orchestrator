"""YouTube channel operations planning and video summary orchestration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_orchestrator.core.security_utils import safe_preview
from scripts.common.youtube_api_common import (
    _now,
    _write_report,
    SENSITIVE_WORDS,
    ROOT,
    LATEST_VIDEO_SUMMARY,
    TRANSCRIPT_SOURCE_POLICY,
    _top_keywords,
    parse_youtube_video_id,
)


COMMENT_ACTION_POLICY = {
    "prepare": {
        "state_change": False,
        "approval_required": False,
        "allowed": True,
    },
    "post": {
        "state_change": True,
        "approval_required": True,
        "approval_boundary": "final_post_comment_button",
        "allowed_without_approval": False,
    },
    "reply": {
        "state_change": True,
        "approval_required": True,
        "approval_boundary": "final_reply_button",
        "allowed_without_approval": False,
    },
    "moderate": {
        "state_change": True,
        "approval_required": True,
        "approval_boundary": "hide_report_delete_or_pin_button",
        "allowed_without_approval": False,
    },
}


def prepare_comment_plan(
    *,
    video_id: str,
    text: str,
    parent_comment_id: str = "",
    action: str = "comment",
) -> tuple[dict[str, Any], Path]:
    """Prepare a YouTube comment/reply plan without posting it."""
    action = action if action in {"comment", "reply"} else "comment"
    clean_text = SENSITIVE_WORDS.sub("[redacted-sensitive]", text).strip()
    missing: list[str] = []
    if not video_id.strip():
        missing.append("video_id")
    if not clean_text:
        missing.append("comment_text")
    if action == "reply" and not parent_comment_id.strip():
        missing.append("parent_comment_id")
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_comment_prepare",
        "ok": not missing,
        "status": "ready_for_approval" if not missing else "blocked",
        "action": action,
        "video_id": safe_preview(video_id, limit=80),
        "parent_comment_id": safe_preview(parent_comment_id, limit=120),
        "comment_text": safe_preview(clean_text, limit=1000),
        "comment_length": len(clean_text),
        "missing_requirements": missing,
        "state_change": False,
        "approval": {
            "required_for_execution": True,
            "approval_boundary": "final_comment_or_reply_button",
            "confirm_phrase": "YOUTUBE_APPROVED_COMMENT",
        },
        "execution": {
            "post_executed": False,
            "reply_executed": False,
            "api_call_allowed_now": False,
        },
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_comment_plan_latest.json", "youtube_comment_plan")


def build_channel_ops_plan(*, workflow: str, video_id: str = "", comment_id: str = "") -> tuple[dict[str, Any], Path]:
    """Describe owner-channel operations and their approval boundaries."""
    state_changing = workflow in {"upload", "publish", "comment_post", "comment_reply", "hide_comment", "delete_comment", "pin_comment"}
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_channel_ops_plan",
        "operation": workflow,
        "video_id": safe_preview(video_id, limit=80),
        "comment_id": safe_preview(comment_id, limit=120),
        "state_change": False,
        "would_change_state_if_executed": state_changing,
        "owner_oauth_required": state_changing,
        "approval_required": state_changing,
        "approval_boundary": "final_confirm_button" if state_changing else "read_only",
        "allowed_now": not state_changing,
        "note": "This plan does not execute YouTube mutations. Final execution requires owner OAuth and explicit approval.",
    }
    return payload, _write_report(payload, ROOT / "data" / "youtube_channel_ops_plan_latest.json", "youtube_channel_ops_plan")


def collect_video_summary_from_url(
    url_or_video_id: str,
    *,
    token_file: str | Path | None = None,
    max_comments: int = 20,
    tfmt: str = "srt",
) -> tuple[dict[str, Any], Path]:
    """Build a compliant summary package for a public YouTube video."""
    from scripts.youtube.research_search import collect_video_info, collect_comments
    from scripts.youtube.research_captions import collect_script_from_url

    video_id = parse_youtube_video_id(url_or_video_id)
    if not video_id:
        payload = {
            "schema_version": 1,
            "created_at": _now(),
            "workflow": "youtube_video_summary",
            "ok": False,
            "status": "blocked",
            "reason": "invalid_youtube_video_url_or_id",
            "input": safe_preview(url_or_video_id, limit=180),
            "state_change": False,
            "secret_values_read": False,
            "next_step": "Provide a YouTube watch, youtu.be, shorts, embed URL, or an 11-character video id.",
        }
        return payload, _write_report(payload, LATEST_VIDEO_SUMMARY, "youtube_video_summary")

    info, info_path = collect_video_info(video_id, token_file=token_file)
    comments, comments_path = collect_comments(video_id, max_results=max_comments, token_file=token_file)
    script, script_path = collect_script_from_url(video_id, token_file=token_file, tfmt=tfmt, analyze=False)

    video = info.get("video", {}) if info.get("status") == "ok" else {}
    comment_rows = comments.get("comments", []) if comments.get("status") == "ok" else []
    source_text = " ".join(
        [
            str(video.get("title", "")),
            str(video.get("description", "")),
            " ".join(str(tag) for tag in video.get("tags", [])),
            " ".join(str(item.get("text", "")) for item in comment_rows[:20]),
        ]
    )
    keywords = _top_keywords(source_text, limit=12)
    transcript_status = script.get("status", "unknown")
    summary_status = "transcript_assisted" if transcript_status == "ok" else "metadata_comment_summary"
    status = "ok" if info.get("status") == "ok" else "partial"
    if info.get("status") != "ok" and comments.get("status") != "ok" and transcript_status != "ok":
        status = "blocked"

    fallback_required = transcript_status != "ok"
    payload = {
        "schema_version": 1,
        "created_at": _now(),
        "workflow": "youtube_video_summary",
        "ok": status != "blocked",
        "status": status,
        "summary_status": summary_status,
        "reason": "" if status != "blocked" else "all_official_summary_sources_unavailable",
        "video_id": safe_preview(video_id, limit=80),
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "state_change": False,
        "secret_values_read": False,
        "oauth_token_output": "redacted",
        "reports": {
            "video_info": str(info_path),
            "comments": str(comments_path),
            "script_collect": str(script_path),
            "transcript_analysis": script.get("analysis_report") or "",
        },
        "source_status": {
            "video_info": info.get("status", "unknown"),
            "comments": comments.get("status", "unknown"),
            "script_collect": transcript_status,
            "script_reason": script.get("reason", ""),
            "caption_count": script.get("caption_count", 0),
        },
        "video": {
            "title": video.get("title", ""),
            "channel_title": video.get("channel_title", ""),
            "published_at": video.get("published_at", ""),
            "duration": video.get("duration", ""),
            "caption_available_hint": video.get("caption_available_hint", ""),
            "statistics": video.get("statistics", {}),
        },
        "summary": {
            "method": summary_status,
            "brief": (
                f"{video.get('channel_title', '-')} channel video about {video.get('title', '-')}"
                if video
                else "Official metadata was unavailable; summary requires a browser-visible transcript or audio summary pass."
            ),
            "topics": [row["keyword"] for row in keywords[:8]],
            "signals": {
                "comment_count_collected": comments.get("comment_count", 0),
                "transcript_word_like_count": script.get("word_like_count", 0),
                "metadata_available": bool(video),
            },
        },
        "fallback_required": fallback_required,
        "fallback_plan": {
            "approved_browser_visible_transcript": fallback_required,
            "approved_local_audio_stt_summary": fallback_required,
            "store_full_third_party_transcript": False,
            "blocked": list(TRANSCRIPT_SOURCE_POLICY["blocked"]),
            "next_step": (
                "Open a user-approved browser transcript/audio summary task and store only derived summary outputs."
                if fallback_required
                else "Use the authorized transcript analysis report for deeper summarization."
            ),
        },
        "copyright_note": "Do not publish copied transcript text without rights review.",
    }
    return payload, _write_report(payload, LATEST_VIDEO_SUMMARY, "youtube_video_summary")
