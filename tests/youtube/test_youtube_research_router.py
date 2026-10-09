from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.youtube.research_router import youtube_research_router
from tools.gates.auth import get_current_user


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(youtube_research_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": "owner"}
    return TestClient(app)


def test_youtube_research_status_route_is_read_only() -> None:
    response = _client().get("/api/v1/youtube/research/status")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True
    assert data["state_change"] is False
    assert "research search" in data["capabilities"]


def test_youtube_search_route_blocks_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_OAUTH_TOKEN_FILE", raising=False)
    import scripts.youtube.research as _r

    monkeypatch.setattr(_r, "_api_key", lambda explicit=None: "")
    monkeypatch.setattr(_r, "_oauth_token", lambda explicit=None, token_file=None: "")

    response = _client().get("/api/v1/youtube/research/search?query=ai&max_results=3&captions_only=true")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["reason"] == "youtube_data_api_key_or_oauth_token_required"
    assert data["state_change"] is False
    assert data["secret_values_read"] is False
    assert "report_path" in data


def test_youtube_transcript_plan_route_blocks_scraping() -> None:
    response = _client().get("/api/v1/youtube/research/transcript-plan?video_id=abc123")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "unofficial_caption_scraping" in data["blocked_next_steps"]
    assert data["state_change"] is False


def test_youtube_context_report_route_builds_scorecard() -> None:
    response = _client().post(
        "/api/v1/youtube/research/context-report",
        json={
            "video_info": {
                "video": {
                    "title": "AI workflow automation",
                    "description": "Browser automation and approval workflows",
                    "caption_available_hint": "true",
                    "statistics": {"view_count": "1000", "like_count": "50", "comment_count": "3"},
                }
            },
            "comments": {"comments": [{"text": "How do I approve safely?", "like_count": 5}]},
            "transcript_text": "AI workflow automation helps users approve actions safely.",
            "topic": "AI workflow automation",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True
    assert data["state_change"] is False
    assert data["context"]["source_counts"]["comments"] == 1
    assert "my_video_opportunity_score" in data["scorecard"]["scores"]
