"""Tests for ai_orchestrator/connectors/naver_search_api_client.py (F-4S-2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from ai_orchestrator.connectors import naver_search_api_client as client_mod
from ai_orchestrator.connectors import naver_search_api_config as cfg_mod


SECRET_ID = "test-client-id-XXX"
SECRET_VALUE = "test-client-secret-YYY"


def _live_cfg() -> cfg_mod.NaverSearchApiConfig:
    return cfg_mod.NaverSearchApiConfig(
        client_id=SECRET_ID,
        client_secret=SECRET_VALUE,
    )


def _empty_cfg() -> cfg_mod.NaverSearchApiConfig:
    return cfg_mod.NaverSearchApiConfig(client_id=None, client_secret=None)


def _capture_transport(captured: List[Dict[str, Any]], *, status: int = 200, body: str = "{}"):
    def transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
        captured.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return status, body
    return transport


# ── normalize_search_type ───────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("blog", "blog"),
        ("BLOG", "blog"),
        ("News", "news"),
        ("cafearticle", "cafearticle"),
        ("cafe", "cafearticle"),
        ("cafe_article", "cafearticle"),
        ("shop", "shop"),
        ("shopping", "shop"),
        ("webkr", "webkr"),
        ("web", "webkr"),
    ],
)
def test_normalize_search_type_maps_aliases(raw, expected):
    assert client_mod.normalize_search_type(raw) == expected


@pytest.mark.parametrize("bad", ["", None, "videos", "image", "kin"])
def test_normalize_search_type_rejects_unsupported(bad):
    with pytest.raises(ValueError):
        client_mod.normalize_search_type(bad)


# ── validate_search_params ──────────────────────────────────────
def test_validate_rejects_empty_query():
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="", display=10, start=1)
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="   ", display=10, start=1)


@pytest.mark.parametrize("display", [0, -1, 101, 9999])
def test_validate_rejects_display_out_of_range(display):
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="x", display=display, start=1)


@pytest.mark.parametrize("start", [0, -1, 1001, 99999])
def test_validate_rejects_start_out_of_range(start):
    with pytest.raises(ValueError):
        client_mod.validate_search_params(query="x", display=10, start=start)


def test_validate_rejects_unsupported_sort_for_type():
    with pytest.raises(ValueError):
        client_mod.validate_search_params(
            query="x", display=10, start=1, sort="asc", search_type="blog"
        )


def test_validate_rejects_sort_for_webkr():
    with pytest.raises(ValueError):
        client_mod.validate_search_params(
            query="x", display=10, start=1, sort="sim", search_type="webkr"
        )


def test_validate_accepts_shop_sort_extras():
    out = client_mod.validate_search_params(
        query="x", display=10, start=1, sort="asc", search_type="shop"
    )
    assert out["sort"] == "asc"


def test_validate_blog_sort_sim_and_date_ok():
    for s in ("sim", "date"):
        out = client_mod.validate_search_params(
            query="x", display=10, start=1, sort=s, search_type="blog"
        )
        assert out["sort"] == s


# ── search_naver: live=False or no keys → mock_or_disabled ──────
def test_live_false_returns_mock_without_calling_transport():
    captured: List[Dict[str, Any]] = []
    cfg = _live_cfg()
    result = client_mod.search_naver(
        search_type="blog",
        query="hello",
        display=5,
        start=1,
        sort="sim",
        live=False,
        config=cfg,
        transport=_capture_transport(captured),
    )
    assert result["mode"] == "mock_or_disabled"
    assert result["items"] == []
    assert captured == []


def test_live_true_without_keys_returns_mock_with_warning():
    captured: List[Dict[str, Any]] = []
    cfg = _empty_cfg()
    result = client_mod.search_naver(
        search_type="blog",
        query="hello",
        display=5,
        live=True,
        config=cfg,
        transport=_capture_transport(captured),
    )
    assert result["mode"] == "mock_or_disabled"
    assert any("missing" in w.lower() for w in (result.get("warnings") or []))
    assert captured == []


# ── search_naver: live=True with keys → calls transport ─────────
def test_live_call_with_keys_passes_secret_via_headers_only():
    captured: List[Dict[str, Any]] = []
    body = json.dumps(
        {
            "lastBuildDate": "now",
            "total": 2,
            "start": 1,
            "display": 2,
            "items": [
                {"title": "A", "link": "https://a.example", "description": "x"},
                {"title": "B", "link": "https://b.example", "description": "y"},
            ],
        },
        ensure_ascii=False,
    )
    result = client_mod.search_naver(
        search_type="blog",
        query="소방",
        display=2,
        live=True,
        config=_live_cfg(),
        transport=_capture_transport(captured, status=200, body=body),
    )
    assert result["mode"] == "live"
    assert result["success"] is True
    assert result["total"] == 2
    assert len(result["items"]) == 2

    assert len(captured) == 1
    call = captured[0]
    assert "/blog.json" in call["url"]
    # secret must NOT appear in the URL
    assert SECRET_ID not in call["url"]
    assert SECRET_VALUE not in call["url"]
    # secret IS present in headers — that is the only allowed channel
    assert call["headers"]["X-Naver-Client-Id"] == SECRET_ID
    assert call["headers"]["X-Naver-Client-Secret"] == SECRET_VALUE


def test_live_http_error_returns_failure_with_no_body_leakage():
    captured: List[Dict[str, Any]] = []
    body_with_secret_like = json.dumps({"errorMessage": "rate limit", "errorCode": "X"})
    result = client_mod.search_naver(
        search_type="news",
        query="abc",
        live=True,
        config=_live_cfg(),
        transport=_capture_transport(captured, status=429, body=body_with_secret_like),
    )
    assert result["success"] is False
    assert result["mode"] == "live"
    assert result["error"] == "http_429"
    # body is summarized by length only — never returned raw
    assert "body" not in result
    assert "body_length" in result


def test_live_transport_exception_is_caught():
    def bad_transport(url, headers, timeout):
        raise ConnectionError("dns_fail")

    result = client_mod.search_naver(
        search_type="shop",
        query="abc",
        live=True,
        config=_live_cfg(),
        transport=bad_transport,
    )
    assert result["success"] is False
    assert result["error"].startswith("transport_error")


def test_live_invalid_json_is_handled():
    result = client_mod.search_naver(
        search_type="webkr",
        query="abc",
        live=True,
        config=_live_cfg(),
        transport=_capture_transport([], status=200, body="not-json{"),
    )
    assert result["success"] is False
    assert result["error"] == "invalid_json"


# ── secret never leaked in any returned value or string repr ────
def test_no_secret_in_returned_payloads_under_any_branch():
    cfg = _live_cfg()

    # mock branch
    r1 = client_mod.search_naver("blog", "q", live=False, config=cfg, transport=_capture_transport([]))
    assert SECRET_ID not in json.dumps(r1) and SECRET_VALUE not in json.dumps(r1)

    # live success
    body = json.dumps({"total": 0, "start": 1, "display": 10, "items": []})
    r2 = client_mod.search_naver("blog", "q", live=True, config=cfg, transport=_capture_transport([], body=body))
    assert SECRET_ID not in json.dumps(r2) and SECRET_VALUE not in json.dumps(r2)

    # live HTTP error
    r3 = client_mod.search_naver("blog", "q", live=True, config=cfg, transport=_capture_transport([], status=500, body="err"))
    assert SECRET_ID not in json.dumps(r3) and SECRET_VALUE not in json.dumps(r3)


# ── module hygiene ──────────────────────────────────────────────
def test_module_does_not_import_browser_or_requests():
    # the module must not pull in browser automation or requests
    src = Path(client_mod.__file__).read_text(encoding="utf-8")
    assert "import requests" not in src
    assert "from requests" not in src
    # check imports specifically — docstring may mention playwright as a banned word
    lowered = src.lower()
    assert "import playwright" not in lowered
    assert "from playwright" not in lowered
    assert "import selenium" not in lowered
    assert "from selenium" not in lowered


def test_module_has_no_cafe_write_actions():
    src = Path(client_mod.__file__).read_text(encoding="utf-8")
    forbidden = ["cafe_join", "cafe_post", "cafe_comment", "join_cafe", "write_post"]
    for token in forbidden:
        assert token not in src, f"forbidden write-action token leaked: {token}"


def test_supported_types_match_endpoints():
    assert set(client_mod.SUPPORTED_TYPES) == set(client_mod.ENDPOINT_BY_TYPE.keys())
