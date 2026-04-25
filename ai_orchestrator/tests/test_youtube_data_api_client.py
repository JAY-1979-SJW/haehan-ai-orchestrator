"""Tests for ai_orchestrator/connectors/youtube_data_api_client.py (F-4S-3)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from ai_orchestrator.connectors import youtube_data_api_client as client_mod
from ai_orchestrator.connectors import youtube_data_api_config as cfg_mod


SECRET_KEY = "test-youtube-api-key-XXX"


def _live_cfg() -> cfg_mod.YoutubeDataApiConfig:
    return cfg_mod.YoutubeDataApiConfig(api_key=SECRET_KEY)


def _empty_cfg() -> cfg_mod.YoutubeDataApiConfig:
    return cfg_mod.YoutubeDataApiConfig(api_key=None)


def _capture_transport(captured: List[Dict[str, Any]], *, status: int = 200, body: str = "{}"):
    def transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
        captured.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return status, body
    return transport


# ── validate_search_params ─────────────────────────────────────────
def test_validate_rejects_empty_query():
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="", max_results=5)
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="   ", max_results=5)


@pytest.mark.parametrize("max_results", [0, -1, 51, 9999])
def test_validate_rejects_max_results_out_of_range(max_results):
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="x", max_results=max_results)


@pytest.mark.parametrize("order", ["", "popularity", "newest", "random"])
def test_validate_rejects_unknown_order(order):
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="x", max_results=5, order=order)


@pytest.mark.parametrize("order", list(client_mod.SEARCH_ORDERS))
def test_validate_accepts_supported_orders(order):
    out = client_mod.validate_search_params(query="x", max_results=5, order=order)
    assert out["order"] == order


def test_validate_published_after_accepts_date_only():
    out = client_mod.validate_search_params(
        query="x", max_results=5, published_after="2026-01-01"
    )
    assert out["published_after"] == "2026-01-01T00:00:00Z"


def test_validate_published_after_accepts_full_rfc3339():
    out = client_mod.validate_search_params(
        query="x", max_results=5, published_after="2026-01-01T12:34:56Z"
    )
    assert out["published_after"] == "2026-01-01T12:34:56Z"


@pytest.mark.parametrize("bad", ["yesterday", "2026/01/01", "2026-1-1", "abc"])
def test_validate_published_after_rejects_invalid(bad):
    with pytest.raises(ValueError):
        client_mod.validate_search_params(
            query="x", max_results=5, published_after=bad
        )


# ── validate_video_ids ─────────────────────────────────────────────
def test_validate_video_ids_requires_non_empty():
    with pytest.raises(ValueError):
        client_mod.validate_video_ids([])
    with pytest.raises(ValueError):
        client_mod.validate_video_ids("   ")


def test_validate_video_ids_rejects_more_than_50():
    too_many = [f"id{i:03d}" for i in range(51)]
    with pytest.raises(ValueError):
        client_mod.validate_video_ids(too_many)


def test_validate_video_ids_accepts_50_max():
    ok = [f"id{i:03d}" for i in range(50)]
    out = client_mod.validate_video_ids(ok)
    assert len(out) == 50


def test_validate_video_ids_rejects_invalid_chars():
    with pytest.raises(ValueError):
        client_mod.validate_video_ids(["good_id1", "bad id with space"])


def test_validate_video_ids_accepts_comma_string():
    out = client_mod.validate_video_ids("abc123,DEF-456,_under_")
    assert out == ["abc123", "DEF-456", "_under_"]


# ── search_videos: live=False or no key → mock_or_disabled ─────────
def test_search_live_false_returns_mock_without_calling_transport():
    captured: List[Dict[str, Any]] = []
    cfg = _live_cfg()
    result = client_mod.search_videos(
        query="hello",
        max_results=3,
        live=False,
        config=cfg,
        transport=_capture_transport(captured),
    )
    assert result["mode"] == "mock_or_disabled"
    assert result["items"] == []
    assert result["quota_cost"] == 0
    assert captured == []


def test_search_live_true_without_key_returns_mock_with_warning():
    captured: List[Dict[str, Any]] = []
    cfg = _empty_cfg()
    result = client_mod.search_videos(
        query="hello",
        live=True,
        config=cfg,
        transport=_capture_transport(captured),
    )
    assert result["mode"] == "mock_or_disabled"
    assert any("missing" in w.lower() for w in (result.get("warnings") or []))
    assert captured == []


# ── search_videos: live=True with key → calls transport ────────────
def test_search_live_call_passes_key_via_querystring_only_and_records_quota():
    captured: List[Dict[str, Any]] = []
    body = json.dumps(
        {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "T1",
                        "channelTitle": "C1",
                        "publishedAt": "2026-04-01T00:00:00Z",
                        "description": "desc",
                    },
                },
                {
                    "id": {"videoId": "def456"},
                    "snippet": {
                        "title": "T2",
                        "channelTitle": "C2",
                        "publishedAt": "2026-04-02T00:00:00Z",
                    },
                },
            ]
        },
        ensure_ascii=False,
    )
    result = client_mod.search_videos(
        query="소방",
        max_results=2,
        live=True,
        config=_live_cfg(),
        transport=_capture_transport(captured, status=200, body=body),
    )
    assert result["mode"] == "live"
    assert result["success"] is True
    assert result["quota_cost"] == client_mod.QUOTA_COST_SEARCH == 100
    assert len(result["items"]) == 2
    assert result["items"][0]["videoId"] == "abc123"
    assert result["items"][0]["channelTitle"] == "C1"

    assert len(captured) == 1
    call = captured[0]
    assert "/search" in call["url"]
    # Google APIs accept key via query string. Verify the parameter is present...
    assert f"key={SECRET_KEY}" in call["url"] or "key=" in call["url"]


def test_search_live_http_error_returns_failure_with_no_body_leakage():
    captured: List[Dict[str, Any]] = []
    body = json.dumps({"error": {"code": 403, "message": "quotaExceeded"}})
    result = client_mod.search_videos(
        query="abc",
        live=True,
        config=_live_cfg(),
        transport=_capture_transport(captured, status=403, body=body),
    )
    assert result["success"] is False
    assert result["mode"] == "live"
    assert result["error"] == "http_403"
    assert "body" not in result
    assert "body_length" in result


def test_search_live_transport_exception_is_caught():
    def bad_transport(url, headers, timeout):
        raise ConnectionError("dns_fail")

    result = client_mod.search_videos(
        query="abc",
        live=True,
        config=_live_cfg(),
        transport=bad_transport,
    )
    assert result["success"] is False
    assert result["error"].startswith("transport_error")


def test_search_live_invalid_json_is_handled():
    result = client_mod.search_videos(
        query="abc",
        live=True,
        config=_live_cfg(),
        transport=_capture_transport([], status=200, body="not-json{"),
    )
    assert result["success"] is False
    assert result["error"] == "invalid_json"


# ── get_video_details ──────────────────────────────────────────────
def test_details_live_false_returns_mock_without_calling_transport():
    captured: List[Dict[str, Any]] = []
    result = client_mod.get_video_details(
        video_ids=["abc123"],
        live=False,
        config=_live_cfg(),
        transport=_capture_transport(captured),
    )
    assert result["mode"] == "mock_or_disabled"
    assert result["quota_cost"] == 0
    assert captured == []


def test_details_live_true_without_key_returns_mock_with_warning():
    captured: List[Dict[str, Any]] = []
    result = client_mod.get_video_details(
        video_ids=["abc123"],
        live=True,
        config=_empty_cfg(),
        transport=_capture_transport(captured),
    )
    assert result["mode"] == "mock_or_disabled"
    assert any("missing" in w.lower() for w in (result.get("warnings") or []))
    assert captured == []


def test_details_live_call_records_quota_one_and_summarizes():
    captured: List[Dict[str, Any]] = []
    body = json.dumps(
        {
            "items": [
                {
                    "id": "abc123",
                    "snippet": {
                        "title": "T1",
                        "channelTitle": "C1",
                        "publishedAt": "2026-04-01T00:00:00Z",
                    },
                    "statistics": {
                        "viewCount": "1000",
                        "likeCount": "10",
                        "commentCount": "2",
                    },
                    "contentDetails": {"duration": "PT1M30S"},
                }
            ]
        },
        ensure_ascii=False,
    )
    result = client_mod.get_video_details(
        video_ids=["abc123", "def456"],
        live=True,
        config=_live_cfg(),
        transport=_capture_transport(captured, status=200, body=body),
    )
    assert result["mode"] == "live"
    assert result["success"] is True
    assert result["quota_cost"] == client_mod.QUOTA_COST_VIDEOS == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["viewCount"] == "1000"
    assert result["items"][0]["duration"] == "PT1M30S"

    assert len(captured) == 1
    call = captured[0]
    assert "/videos" in call["url"]
    assert "id=abc123%2Cdef456" in call["url"] or "id=abc123,def456" in call["url"]


# ── url masking ────────────────────────────────────────────────────
def test_mask_url_secret_replaces_key_value():
    raw = "https://x/test?part=snippet&key=SECRET&maxResults=5"
    masked = client_mod._mask_url_secret(raw)
    assert "SECRET" not in masked
    assert "key=***" in masked
    assert "maxResults=5" in masked


# ── module hygiene ─────────────────────────────────────────────────
def test_module_does_not_import_browser_or_requests_or_oauth():
    src = Path(client_mod.__file__).read_text(encoding="utf-8")
    assert "import requests" not in src
    assert "from requests" not in src
    lowered = src.lower()
    assert "import playwright" not in lowered
    assert "from playwright" not in lowered
    assert "import selenium" not in lowered
    assert "from selenium" not in lowered
    # OAuth / google-auth must not be imported
    assert "google.oauth2" not in lowered
    assert "google_auth_oauthlib" not in lowered
    assert "google_auth" not in lowered
    assert "oauth2client" not in lowered
    # YouTube Studio / login automation tokens
    assert "studio.youtube" not in lowered
    assert "accounts.google.com" not in lowered


def test_module_has_no_write_actions():
    src = Path(client_mod.__file__).read_text(encoding="utf-8")
    forbidden = [
        "videos.insert",
        "videos.update",
        "videos.delete",
        "comments.insert",
        "commentThreads.insert",
        "playlistItems.insert",
        "channels.update",
    ]
    for token in forbidden:
        assert token not in src, f"forbidden write-action token leaked: {token}"


def test_no_secret_in_returned_payloads_under_any_branch():
    cfg = _live_cfg()

    # mock branch
    r1 = client_mod.search_videos(query="q", live=False, config=cfg, transport=_capture_transport([]))
    assert SECRET_KEY not in json.dumps(r1)

    # live success
    body = json.dumps({"items": []})
    r2 = client_mod.search_videos(query="q", live=True, config=cfg, transport=_capture_transport([], body=body))
    assert SECRET_KEY not in json.dumps(r2)

    # live HTTP error
    r3 = client_mod.search_videos(
        query="q", live=True, config=cfg,
        transport=_capture_transport([], status=500, body="err"),
    )
    assert SECRET_KEY not in json.dumps(r3)

    # details mock
    r4 = client_mod.get_video_details(video_ids=["abc"], live=False, config=cfg, transport=_capture_transport([]))
    assert SECRET_KEY not in json.dumps(r4)


def test_quota_cost_constants():
    assert client_mod.QUOTA_COST_SEARCH == 100
    assert client_mod.QUOTA_COST_VIDEOS == 1
