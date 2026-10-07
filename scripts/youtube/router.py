"""YouTube recording/upload router."""
from __future__ import annotations

from . import browser_transcript, oauth, recording, research, uploader
from .gates import gate_youtube_upload_plan, gate_youtube_publish_plan  # noqa: F401
from .site_profile import YOUTUBE_PROFILE  # noqa: F401
from .validators import validate_youtube_no_plain_secret  # noqa: F401

__status__ = {
    "tasks": {
        "record prepare": "done",
        "record execute": "approval_gated",
        "upload prepare": "done",
        "upload execute": "approval_gated",
        "upload verify": "done",
        "oauth start": "done_user_approval_url",
        "oauth exchange": "done_user_code_exchange",
        "research search": "done_official_api",
        "research video-info": "done_official_api",
        "research comments": "done_official_api",
        "research transcript-plan": "done_policy_gated",
        "research script-collect": "done_official_oauth",
        "research video-summary": "done_official_sources_with_fallback_plan",
        "research browser-transcript-summary": "done_user_present_visible_transcript",
        "research caption-list": "done_official_oauth",
        "research caption-download": "done_official_oauth",
        "research analyze": "done_user_transcript",
        "research context-report": "done_metadata_comments_transcript",
        "research scorecard": "done_strategy_scoring",
        "research comment-plan": "done_prepare_only",
        "research channel-ops-plan": "done_approval_boundary",
    },
    "note": "Recording and upload are separated. Upload defaults to dry-run and requires explicit approval.",
}


def run_youtube(task: str, sub: str, args: list[str]) -> None:
    match task:
        case "record" | "recording":
            _cmd_record(sub or "prepare", args)
        case "upload":
            _cmd_upload(sub or "prepare", args)
        case "oauth" | "auth":
            _cmd_oauth(sub or "start", args)
        case "research" | "analyze":
            _cmd_research(sub or "search", args)
        case "status":
            print(__status__)
        case _:
            print(f"  [error] unknown youtube task: {task}")


def _cmd_record(sub: str, args: list[str]) -> None:
    if sub == "prepare":
        values = uploader.parse_kv_args(args)
        plan, path = recording.prepare_recording_plan(values)
        print("=" * 60)
        print("YouTube recording prepare")
        print("=" * 60)
        print(f"ready_for_approval: {plan['ready_for_approval']}")
        print(f"output: {plan['recording']['output_path']}")
        print(f"ffmpeg_found: {plan['recording']['ffmpeg_found']}")
        print(f"saved: {path}")
        print(f"execute: python scripts\\entry\\cdp_cli.py youtube record execute {path} --approved --confirm={recording.APPROVAL_PHRASE}")
        return
    if sub == "execute":
        if not args:
            print("  [error] usage: youtube record execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_RECORD")
            return
        plan_path = args[0]
        approved = "--approved" in args
        confirm = _confirm_arg(args)
        result, path = recording.execute_recording_plan(plan_path, approved=approved, confirm=confirm)
        print("=" * 60)
        print("YouTube recording execute")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"state_change: {result['state_change']}")
        print(f"output: {result['output_path']}")
        print(f"saved: {path}")
        return
    print(f"  [error] unknown youtube record task: {sub}")


def _cmd_upload(sub: str, args: list[str]) -> None:
    if sub == "prepare":
        if not args:
            print("  [error] usage: youtube upload prepare <local_video> title=... description=... privacy=private")
            return
        local_path = args[0]
        values = uploader.parse_kv_args(args[1:])
        plan, path = uploader.prepare_upload_plan(local_path, values)
        print("=" * 60)
        print("YouTube upload prepare")
        print("=" * 60)
        print(f"ready_for_approval: {plan['ready_for_approval']}")
        print(f"local_path: {plan['local_path']}")
        print(f"privacy: {plan['metadata']['privacy_status']}")
        print(f"missing: {', '.join(plan['missing_requirements']) or '-'}")
        print(f"saved: {path}")
        print(f"dry-run execute: python scripts\\entry\\cdp_cli.py youtube upload execute {path} --approved --confirm={uploader.APPROVAL_PHRASE} --dry-run")
        return
    if sub == "execute":
        if not args:
            print("  [error] usage: youtube upload execute <plan_path> --approved --confirm=YOUTUBE_APPROVED_UPLOAD [--dry-run|--live]")
            return
        plan_path = args[0]
        approved = "--approved" in args
        confirm = _confirm_arg(args)
        dry_run = "--live" not in args
        result, path = uploader.execute_upload_plan(plan_path, approved=approved, confirm=confirm, dry_run=dry_run)
        print("=" * 60)
        print("YouTube upload execute")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"state_change: {result['state_change']}")
        print(f"dry_run: {result['dry_run']}")
        print(f"video_id: {result.get('video_id') or '-'}")
        print(f"reason: {result.get('reason') or '-'}")
        print(f"saved: {path}")
        return
    if sub == "verify":
        if not args:
            print("  [error] usage: youtube upload verify <result_path>")
            return
        verification, path = uploader.verify_upload_result(args[0])
        print("=" * 60)
        print("YouTube upload verify")
        print("=" * 60)
        print(f"status: {verification['status']}")
        print(f"video_id: {verification.get('video_id') or '-'}")
        print(f"saved: {path}")
        return
    print(f"  [error] unknown youtube upload task: {sub}")


def _cmd_oauth(sub: str, args: list[str]) -> None:
    values = oauth.parse_kv_args(args)
    if sub in ("server-preapproval", "server-approval", "caption-server-preapproval"):
        result, path = oauth.build_server_preapproval(values)
        print("=" * 60)
        print("YouTube server OAuth preapproval")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"user_approval_mode: {result['user_approval_mode']}")
        print(f"project: {result['google_cloud_inputs']['project']}")
        print(f"application_type: {result['google_cloud_inputs']['application_type']}")
        print(f"client_name: {result['google_cloud_inputs']['client_name']}")
        print(f"redirect_uri: {result['google_cloud_inputs']['authorized_redirect_uri']}")
        print(f"scope: {result['google_cloud_inputs']['scope']}")
        print(f"client_json_path: {result['server_secret_placement']['client_json_path']}")
        print(f"token_file_path: {result['server_secret_placement']['token_file_path']}")
        print(f"saved: {path}")
        return
    if sub in ("start", "url", "authorize", "auth-url"):
        result, path = oauth.build_auth_plan(values)
        print("=" * 60)
        print("YouTube OAuth authorization")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"reason: {result.get('reason') or '-'}")
        print(f"redirect_uri: {result.get('redirect_uri') or '-'}")
        print(f"scope: {result.get('scope') or '-'}")
        print(f"saved: {path}")
        if result["status"] == "ready_for_user_approval":
            print("auth_url:")
            print(result["auth_url"])
            print("exchange: python scripts\\entry\\cdp_cli.py youtube oauth exchange code=<returned_code> client_file=<client_secret.json>")
        return
    if sub in ("exchange", "token"):
        result, path = oauth.exchange_code(values)
        print("=" * 60)
        print("YouTube OAuth token exchange")
        print("=" * 60)
        print(f"status: {result['status']}")
        print(f"reason: {result.get('reason') or '-'}")
        print(f"refresh_token_present: {result.get('refresh_token_present', False)}")
        print(f"token_file: {result.get('token_file') or '-'}")
        print(f"saved: {path}")
        return
    print(f"  [error] unknown youtube oauth task: {sub}")


def _confirm_arg(args: list[str]) -> str:
    for arg in args:
        if arg.startswith("--confirm="):
            return arg.split("=", 1)[1]
    return ""


def _research_search(values):
    query = values.get("query", "")
    if not query:
        print("  [error] usage: youtube research search query=... [max=5]")
        return
    captions_only = values.get("captions") in {"1", "true", "only", "closedCaption"} or values.get("captions_only") == "1"
    result, path = research.search_videos(
        query,
        max_results=int(values.get("max") or values.get("limit") or 5),
        token_file=values.get("token_file") or values.get("token"),
        captions_only=captions_only,
    )
    print("=" * 60)
    print("YouTube research search")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"result_count: {result.get('result_count', 0)}")
    print(f"captions_only: {result.get('captions_only', False)}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"saved: {path}")
    for item in result.get("results", [])[:10]:
        print(f"- {item['video_id']} | {item['title']} | captions={item.get('caption_available_hint') or '-'}")


def _research_transcript_plan(values, args):
    video_id = values.get("video_id") or values.get("id") or (args[0] if args and "=" not in args[0] else "")
    result, path = research.build_transcript_collection_plan(video_id, owned=values.get("owned") == "1")
    print("=" * 60)
    print("YouTube transcript collection plan")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"video_id: {result['video_id']}")
    print("allowed: user transcript file, owner/OAuth caption file, manually exported caption file")
    print("blocked: unofficial caption scraping")
    print(f"saved: {path}")


def _research_script_collect(values, args):
    source = (
        values.get("url")
        or values.get("video_url")
        or values.get("video_id")
        or values.get("id")
        or values.get("query")
        or (args[0] if args and "=" not in args[0] else "")
    )
    if not source:
        print("  [error] usage: youtube research script-collect url=<youtube_url> [token_file=...] [tfmt=srt] [analyze=1]")
        return
    result, path = research.collect_script_from_url(
        source,
        tfmt=values.get("tfmt", "srt"),
        token_file=values.get("token_file") or values.get("token"),
        analyze=values.get("analyze") in {"1", "true", "yes"},
    )
    print("=" * 60)
    print("YouTube script collect")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"video_id: {result.get('video_id') or '-'}")
    print(f"caption_count: {result.get('caption_count', 0)}")
    print(f"transcript_path: {result.get('transcript_path') or '-'}")
    print(f"analysis_report: {result.get('analysis_report') or '-'}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"next_step: {result.get('next_step') or '-'}")
    print(f"saved: {path}")


def _research_video_summary(values, args):
    source = (
        values.get("url")
        or values.get("video_url")
        or values.get("video_id")
        or values.get("id")
        or values.get("query")
        or (args[0] if args and "=" not in args[0] else "")
    )
    if not source:
        print("  [error] usage: youtube research video-summary url=<youtube_url> [token_file=...] [comments=20]")
        return
    result, path = research.collect_video_summary_from_url(
        source,
        token_file=values.get("token_file") or values.get("token"),
        max_comments=int(values.get("comments") or values.get("max_comments") or 20),
        tfmt=values.get("tfmt", "srt"),
    )
    print("=" * 60)
    print("YouTube video summary")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"summary_status: {result.get('summary_status') or '-'}")
    print(f"video_id: {result.get('video_id') or '-'}")
    print(f"title: {result.get('video', {}).get('title') or '-'}")
    print(f"topics: {', '.join(result.get('summary', {}).get('topics', [])) or '-'}")
    print(f"script_status: {result.get('source_status', {}).get('script_collect') or '-'}")
    print(f"fallback_required: {result.get('fallback_required', False)}")
    print(f"next_step: {result.get('fallback_plan', {}).get('next_step') or '-'}")
    print(f"saved: {path}")


def _research_browser_transcript_summary(values, args):
    source = (
        values.get("url")
        or values.get("video_url")
        or values.get("video_id")
        or values.get("id")
        or values.get("query")
        or (args[0] if args and "=" not in args[0] else "")
    )
    if not source:
        print("  [error] usage: youtube research browser-transcript-summary url=<youtube_url> [max_segments=160]")
        return
    result, path = browser_transcript.collect_visible_transcript_summary(
        source,
        max_segments=int(values.get("max_segments") or values.get("segments") or 160),
        wait_seconds=float(values.get("wait") or values.get("wait_seconds") or 4),
        open_transcript=values.get("open_transcript", "1") not in {"0", "false", "no"},
        cdp_ports=values.get("cdp_ports") or values.get("ports") or values.get("cdp_port"),
    )
    print("=" * 60)
    print("YouTube browser visible transcript summary")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"video_id: {result.get('video_id') or '-'}")
    print(f"segments: {result.get('segment_count_observed', 0)}")
    print(f"words: {result.get('word_like_count', 0)}")
    print(f"topics: {', '.join(result.get('derived_summary', {}).get('topics', [])) or '-'}")
    print(f"raw_transcript_stored: {result.get('raw_transcript_stored', False)}")
    print(f"selected_cdp_port: {result.get('cdp_selection', {}).get('selected_cdp_port') or '-'}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"next_step: {result.get('next_step') or '-'}")
    print(f"saved: {path}")


def _research_caption_list(values, args):
    video_id = values.get("video_id") or values.get("id") or (args[0] if args and "=" not in args[0] else "")
    if not video_id:
        print("  [error] usage: youtube research caption-list video_id=... [token_file=...]")
        return
    result, path = research.list_captions(
        video_id,
        token_file=values.get("token_file") or values.get("token"),
    )
    print("=" * 60)
    print("YouTube caption list")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"caption_count: {result.get('caption_count', 0)}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"saved: {path}")
    for item in result.get("captions", [])[:10]:
        print(f"- {item['caption_id']} | {item.get('language') or '-'} | {item.get('name') or '-'}")


def _research_caption_download(values, args):
    caption_id = values.get("caption_id") or values.get("id") or (args[0] if args and "=" not in args[0] else "")
    if not caption_id:
        print("  [error] usage: youtube research caption-download caption_id=... [tfmt=srt] [token_file=...] [analyze=1]")
        return
    result, path = research.download_caption(
        caption_id,
        tfmt=values.get("tfmt", "srt"),
        token_file=values.get("token_file") or values.get("token"),
        output=values.get("output") or None,
    )
    print("=" * 60)
    print("YouTube caption download")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"caption_id: {result.get('caption_id') or '-'}")
    print(f"transcript_path: {result.get('transcript_path') or '-'}")
    print(f"characters: {result.get('character_count', 0)}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"saved: {path}")
    if result.get("status") == "ok" and values.get("analyze") in {"1", "true", "yes"}:
        analysis, analysis_path = research.analyze_transcript(
            result["transcript_path"],
            video_id=values.get("video_id", ""),
            title=values.get("title", ""),
        )
        print(f"analysis_status: {analysis['status']}")
        print(f"analysis_saved: {analysis_path}")


def _research_store_transcript(values):
    transcript_file = values.get("transcript") or values.get("transcript_file") or values.get("file")
    if not transcript_file:
        print("  [error] usage: youtube research store-transcript transcript=<path> rights_confirmed=1 [video_id=...] [title=...]")
        return
    result, path = research.store_full_transcript_file(
        transcript_file,
        video_id=values.get("video_id", ""),
        title=values.get("title", ""),
        rights_confirmed=values.get("rights_confirmed", values.get("rights", "0")) in {"1", "true", "yes", "confirmed"},
        source_type=values.get("source_type", "user_provided_or_licensed"),
        output=values.get("output") or None,
    )
    print("=" * 60)
    print("YouTube full transcript store")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"full_transcript_stored: {result.get('full_transcript_stored', False)}")
    print(f"raw_transcript_path: {result.get('raw_transcript_path') or '-'}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"saved: {path}")


def _research_video_info(values, args):
    video_id = values.get("video_id") or values.get("id") or (args[0] if args and "=" not in args[0] else "")
    if not video_id:
        print("  [error] usage: youtube research video-info video_id=...")
        return
    result, path = research.collect_video_info(video_id)
    print("=" * 60)
    print("YouTube video info")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"title: {result.get('video', {}).get('title', '-') if result.get('video') else '-'}")
    print(f"caption: {result.get('video', {}).get('caption_available_hint', '-') if result.get('video') else '-'}")
    print(f"saved: {path}")


def _research_comments(values, args):
    video_id = values.get("video_id") or values.get("id") or (args[0] if args and "=" not in args[0] else "")
    if not video_id:
        print("  [error] usage: youtube research comments video_id=... [max=20]")
        return
    result, path = research.collect_comments(
        video_id,
        max_results=int(values.get("max") or values.get("limit") or 20),
        max_pages=int(values.get("pages") or values.get("max_pages") or 1),
        max_comments_total=int(values.get("total") or values.get("max_total") or values.get("max_comments_total") or 100),
        include_replies=values.get("include_replies", values.get("replies", "0")) in {"1", "true", "yes"},
        order=values.get("order", "relevance"),
    )
    print("=" * 60)
    print("YouTube comments")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"comment_count: {result.get('comment_count', 0)}")
    print(f"pages_fetched: {result.get('pages_fetched', 0)}")
    print(f"next_page_token_present: {result.get('next_page_token_present', False)}")
    print(f"reason: {result.get('reason') or '-'}")
    print(f"saved: {path}")


def _research_analyze(values):
    transcript_file = values.get("transcript") or values.get("transcript_file") or values.get("file")
    if not transcript_file:
        print("  [error] usage: youtube research analyze transcript=<path> [video_id=...] [title=...]")
        return
    result, path = research.analyze_transcript(
        transcript_file,
        video_id=values.get("video_id", ""),
        title=values.get("title", ""),
    )
    print("=" * 60)
    print("YouTube transcript analysis")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"words: {result['transcript_stats']['word_like_count']}")
    print("topics: " + ", ".join(result["business_report"]["main_topics"]))
    print(f"saved: {path}")


def _research_context_report(values):
    from pathlib import Path

    info_path = values.get("info") or values.get("video_info")
    comments_path = values.get("comments")
    transcript_file = values.get("transcript") or ""
    video_info = _read_json_file(info_path) if info_path else {}
    comments = _read_json_file(comments_path) if comments_path else {}
    transcript_text = Path(transcript_file).read_text(encoding="utf-8", errors="replace") if transcript_file else ""
    result, path = research.analyze_video_context(
        video_info=video_info,
        comments=comments,
        transcript_text=transcript_text,
    )
    print("=" * 60)
    print("YouTube video context analysis")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"comments: {result['source_counts']['comments']}")
    print("topics: " + ", ".join(row["keyword"] for row in result["top_keywords"][:8]))
    print(f"saved: {path}")


def _research_scorecard(values):
    from pathlib import Path

    info_path = values.get("info") or values.get("video_info")
    comments_path = values.get("comments")
    transcript_file = values.get("transcript") or ""
    video_info = _read_json_file(info_path) if info_path else {}
    comments = _read_json_file(comments_path) if comments_path else {}
    transcript_text = Path(transcript_file).read_text(encoding="utf-8", errors="replace") if transcript_file else ""
    result, path = research.build_video_strategy_scorecard(
        video_info=video_info,
        comments=comments,
        transcript_text=transcript_text,
        channel_topic=values.get("topic", ""),
    )
    print("=" * 60)
    print("YouTube video strategy scorecard")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"opportunity: {result['scores']['my_video_opportunity_score']}")
    print(f"management: {result['scores']['my_video_management_score']}")
    print("actions: " + ", ".join(result["recommended_actions"]))
    print(f"saved: {path}")


def _research_comment_plan(values, sub):
    video_id = values.get("video_id") or values.get("id") or ""
    parent_comment_id = values.get("parent_comment_id") or values.get("comment_id") or ""
    text = values.get("text") or values.get("comment") or values.get("body") or ""
    result, path = research.prepare_comment_plan(
        video_id=video_id,
        parent_comment_id=parent_comment_id,
        text=text,
        action="reply" if sub == "reply-plan" else "comment",
    )
    print("=" * 60)
    print("YouTube comment plan")
    print("=" * 60)
    print(f"status: {result['status']}")
    print(f"action: {result['action']}")
    print(f"approval_required_for_execution: {result['approval']['required_for_execution']}")
    print(f"state_change: {result['state_change']}")
    print(f"saved: {path}")


def _research_channel_ops_plan(values):
    workflow = values.get("workflow") or values.get("operation") or "read"
    result, path = research.build_channel_ops_plan(
        workflow=workflow,
        video_id=values.get("video_id", ""),
        comment_id=values.get("comment_id", ""),
    )
    print("=" * 60)
    print("YouTube channel operations plan")
    print("=" * 60)
    print(f"operation: {result['operation']}")
    print(f"approval_required: {result['approval_required']}")
    print(f"owner_oauth_required: {result['owner_oauth_required']}")
    print(f"allowed_now: {result['allowed_now']}")
    print(f"saved: {path}")


_RESEARCH_HANDLERS = (
    (("search", "find"), lambda v, a, s: _research_search(v)),
    (("transcript-plan", "script-plan", "caption-plan"), lambda v, a, s: _research_transcript_plan(v, a)),
    (
        ("script-collect", "collect-script", "script", "transcript-collect"),
        lambda v, a, s: _research_script_collect(v, a),
    ),
    (("video-summary", "summary", "summarize", "summarise"), lambda v, a, s: _research_video_summary(v, a)),
    (
        ("browser-transcript-summary", "visible-transcript-summary", "deep-summary"),
        lambda v, a, s: _research_browser_transcript_summary(v, a),
    ),
    (("caption-list", "captions", "caption-tracks"), lambda v, a, s: _research_caption_list(v, a)),
    (("caption-download", "download-caption"), lambda v, a, s: _research_caption_download(v, a)),
    (
        ("store-transcript", "full-transcript-store", "store-full-transcript"),
        lambda v, a, s: _research_store_transcript(v),
    ),
    (("video-info", "info", "metadata"), lambda v, a, s: _research_video_info(v, a)),
    (("comments", "comment-list"), lambda v, a, s: _research_comments(v, a)),
    (("analyze", "analyse", "report"), lambda v, a, s: _research_analyze(v)),
    (("context-report", "context", "video-report"), lambda v, a, s: _research_context_report(v)),
    (("scorecard", "strategy-score", "production-score"), lambda v, a, s: _research_scorecard(v)),
    (("comment-plan", "reply-plan"), lambda v, a, s: _research_comment_plan(v, s)),
    (("channel-ops-plan", "ops-plan", "manage-plan"), lambda v, a, s: _research_channel_ops_plan(v)),
)


def _cmd_research(sub: str, args: list[str]) -> None:
    values = research.parse_kv_args(args)
    for names, handler in _RESEARCH_HANDLERS:
        if sub in names:
            handler(values, args, sub)
            return
    print(f"  [error] unknown youtube research task: {sub}")



def _read_json_file(path: str) -> dict:
    import json
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
