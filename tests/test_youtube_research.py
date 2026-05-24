from __future__ import annotations

from pathlib import Path

from scripts.youtube import research
from scripts.youtube.router import _read_json_file


def test_search_blocks_without_api_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_YOUTUBE_API_KEY", raising=False)
    result, path = research.search_videos("ai browser automation", max_results=3, captions_only=True)

    assert path.exists()
    assert result["status"] == "blocked"
    assert result["state_change"] is False
    assert result["reason"] == "youtube_data_api_key_required"
    assert result["captions_only"] is True


def test_search_uses_caption_filter_and_keeps_captioned_results(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append((url, params))
        if url.endswith("/search"):
            return {
                "items": [
                    {"id": {"videoId": "captioned"}, "snippet": {"title": "A", "channelTitle": "C"}},
                    {"id": {"videoId": "plain"}, "snippet": {"title": "B", "channelTitle": "C"}},
                ]
            }
        return {
            "items": [
                {"id": "captioned", "contentDetails": {"caption": "true"}, "statistics": {}},
                {"id": "plain", "contentDetails": {"caption": "false"}, "statistics": {}},
            ]
        }

    monkeypatch.setattr(research, "_api_key", lambda explicit=None: "fake-key")
    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result, _path = research.search_videos("ai", captions_only=True)

    assert calls[0][1]["videoCaption"] == "closedCaption"
    assert result["captions_only"] is True
    assert result["result_count"] == 1
    assert result["results"][0]["video_id"] == "captioned"
    assert result["results"][0]["script_collection_status"] == "caption_candidate"


def test_transcript_plan_blocks_unofficial_scraping():
    result, path = research.build_transcript_collection_plan("abc123")

    assert path.exists()
    assert result["ok"] is True
    assert "unofficial_caption_scraping" in result["blocked_next_steps"]
    assert "user_provided_transcript_file" in result["allowed_next_steps"]
    assert result["state_change"] is False


def test_collect_video_info_uses_official_api(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append((url, params))
        return {
            "items": [
                {
                    "id": "abc123",
                    "snippet": {"title": "Demo", "channelTitle": "Channel", "description": "Desc"},
                    "contentDetails": {"caption": "true", "duration": "PT1M"},
                    "statistics": {"viewCount": "10", "commentCount": "2"},
                }
            ]
        }

    monkeypatch.setattr(research, "_api_key", lambda explicit=None: "fake-key")
    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result, _path = research.collect_video_info("abc123")

    assert calls[0][0].endswith("/videos")
    assert calls[0][1]["part"] == "snippet,contentDetails,statistics"
    assert result["status"] == "ok"
    assert result["video"]["caption_available_hint"] == "true"


def test_collect_comments_uses_official_api(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append((url, params))
        return {
            "items": [
                {
                    "id": "comment-1",
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "authorDisplayName": "User",
                                "textDisplay": "Great automation insight",
                                "likeCount": 3,
                            }
                        }
                    },
                }
            ]
        }

    monkeypatch.setattr(research, "_api_key", lambda explicit=None: "fake-key")
    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result, _path = research.collect_comments("abc123", max_results=5)

    assert calls[0][0].endswith("/commentThreads")
    assert calls[0][1]["textFormat"] == "plainText"
    assert result["comment_count"] == 1
    assert result["comments"][0]["text"] == "Great automation insight"


def test_analyze_user_provided_transcript(tmp_path: Path):
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(
        "This video explains YouTube search automation. "
        "YouTube transcript analysis helps summarize video topics. "
        "Do not publish copied transcript text without rights review.",
        encoding="utf-8",
    )

    result, path = research.analyze_transcript(transcript, video_id="abc123", title="Demo")

    assert path.exists()
    assert result["status"] == "ok"
    assert result["state_change"] is False
    assert result["transcript_stats"]["word_like_count"] > 5
    assert result["business_report"]["main_topics"]


def test_analyze_redacts_sensitive_keywords(tmp_path: Path):
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("The password and bearer token should not be exposed.", encoding="utf-8")

    result, _path = research.analyze_transcript(transcript)
    rendered = str(result).lower()

    assert "password" not in rendered
    assert "bearer" not in rendered
    assert "token" not in rendered


def test_analyze_video_context_combines_video_and_comments():
    result, path = research.analyze_video_context(
        video_info={
            "video": {
                "title": "AI Browser Automation",
                "channel_title": "Demo",
                "caption_available_hint": "true",
                "statistics": {"view_count": "10"},
            }
        },
        comments={"comments": [{"text": "Automation saves time", "like_count": 5, "author_display_name": "A"}]},
        transcript_text="Browser agents automate search and reporting.",
    )

    assert path.exists()
    assert result["status"] == "ok"
    assert result["source_counts"]["comments"] == 1
    assert result["source_counts"]["has_transcript"] is True
    assert result["top_keywords"]


def test_prepare_comment_plan_never_posts():
    result, path = research.prepare_comment_plan(video_id="abc123", text="Thanks for the useful video")

    assert path.exists()
    assert result["status"] == "ready_for_approval"
    assert result["state_change"] is False
    assert result["execution"]["api_call_allowed_now"] is False
    assert result["approval"]["required_for_execution"] is True


def test_channel_ops_plan_gates_state_changing_work():
    result, path = research.build_channel_ops_plan(workflow="comment_reply", video_id="abc123", comment_id="c1")

    assert path.exists()
    assert result["would_change_state_if_executed"] is True
    assert result["approval_required"] is True
    assert result["owner_oauth_required"] is True
    assert result["allowed_now"] is False


def test_strategy_scorecard_scores_reference_video():
    result, path = research.build_video_strategy_scorecard(
        video_info={
            "video": {
                "title": "AI Browser Automation for Small Business",
                "description": "Automate browser research and reporting.",
                "channel_title": "Competitor",
                "caption_available_hint": "true",
                "statistics": {"view_count": "10000", "like_count": "500", "comment_count": "12"},
            }
        },
        comments={
            "status": "ok",
            "comments": [
                {"text": "How can I use this for my business?", "like_count": 8},
                {"text": "Please make a tutorial for browser automation.", "like_count": 5},
            ],
        },
        transcript_text="AI browser automation helps users search, summarize, and report repeated web tasks.",
        channel_topic="AI browser automation business reporting",
    )

    assert path.exists()
    assert result["state_change"] is False
    assert result["scores"]["my_video_opportunity_score"] > 0
    assert result["scores"]["my_video_management_score"] > 0
    assert result["recommended_actions"]
    assert "produce_video" in result["recommended_actions"] or "prepare_script_outline" in result["recommended_actions"]


def test_router_json_reader_accepts_utf8_bom(tmp_path: Path):
    path = tmp_path / "bom.json"
    path.write_text('{"ok": true}', encoding="utf-8-sig")

    assert _read_json_file(str(path)) == {"ok": True}
