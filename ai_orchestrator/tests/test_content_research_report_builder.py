"""Tests for ai_orchestrator/content_research/report_builder.py (F-4S-4)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from ai_orchestrator.connectors import naver_search_api_config as naver_cfg_mod
from ai_orchestrator.connectors import youtube_data_api_config as yt_cfg_mod
from ai_orchestrator.content_research import report_builder as rb


SECRET_NAVER_ID = "test-naver-client-id-XXX"
SECRET_NAVER_SECRET = "test-naver-client-secret-XXX"
SECRET_YT_KEY = "test-youtube-api-key-XXX"


def _live_naver_cfg() -> naver_cfg_mod.NaverSearchApiConfig:
    return naver_cfg_mod.NaverSearchApiConfig(
        client_id=SECRET_NAVER_ID, client_secret=SECRET_NAVER_SECRET
    )


def _empty_naver_cfg() -> naver_cfg_mod.NaverSearchApiConfig:
    return naver_cfg_mod.NaverSearchApiConfig(client_id=None, client_secret=None)


def _live_yt_cfg() -> yt_cfg_mod.YoutubeDataApiConfig:
    return yt_cfg_mod.YoutubeDataApiConfig(api_key=SECRET_YT_KEY)


def _empty_yt_cfg() -> yt_cfg_mod.YoutubeDataApiConfig:
    return yt_cfg_mod.YoutubeDataApiConfig(api_key=None)


# ---------------------------------------------------------------------------
# normalize_keywords
# ---------------------------------------------------------------------------


def test_normalize_keywords_strips_dedupes_drops_empty():
    raw = ["  소방공사 ", "소방공사", "스마트팩토리", "", None, "  ", "Smart  Factory"]
    out = rb.normalize_keywords(raw)
    assert out == ["소방공사", "스마트팩토리", "Smart Factory"]


def test_normalize_keywords_handles_none_input():
    assert rb.normalize_keywords(None) == []


def test_normalize_keywords_lower_case_dedupe():
    out = rb.normalize_keywords(["Foo", "foo", "FOO"])
    assert out == ["Foo"]


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags_and_unescapes():
    s = "<b>소방</b>공사 &amp; 시공 <em>가이드</em>"
    out = rb._strip_html(s)
    assert out == "소방공사 & 시공 가이드"


def test_strip_html_truncates_with_ellipsis():
    s = "a" * 500
    out = rb._strip_html(s, max_len=10)
    assert out.endswith("…")
    assert len(out) <= 11


# ---------------------------------------------------------------------------
# Naver collection (mock disabled)
# ---------------------------------------------------------------------------


def test_collect_naver_results_dry_run_returns_mock_or_disabled():
    block = rb.collect_naver_results(
        keyword="소방공사",
        search_types=["blog", "news"],
        display=3,
        live=False,
        config=_empty_naver_cfg(),
    )
    assert block["keyword"] == "소방공사"
    assert block["normalized_types"] == ["blog", "news"]
    assert block["success_any"] is True
    for nt in ("blog", "news"):
        r = block["results"][nt]
        assert r["mode"] == "mock_or_disabled"
        assert r["items"] == []
    assert any("live=False" in w for w in block["warnings"])


def test_collect_naver_results_live_with_fake_transport():
    payload = {
        "total": 2,
        "start": 1,
        "display": 5,
        "items": [
            {
                "title": "<b>소방</b>공사 가이드",
                "link": "https://blog.example.com/1",
                "description": "공사 <em>핵심</em> 정리",
                "postdate": "20260420",
                "bloggername": "tester",
            },
            {
                "title": "소방공사 사례",
                "link": "https://blog.example.com/2",
                "description": "사례 정리",
                "postdate": "20260421",
                "bloggername": "tester2",
            },
        ],
    }

    captured: List[Dict[str, Any]] = []

    def transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
        captured.append({"url": url, "headers": headers})
        return 200, json.dumps(payload)

    block = rb.collect_naver_results(
        keyword="소방공사",
        search_types=["blog"],
        display=5,
        live=True,
        config=_live_naver_cfg(),
        transport=transport,
    )
    assert block["success_any"] is True
    blog = block["results"]["blog"]
    assert blog["mode"] == "live"
    assert len(blog["items"]) == 2


def test_collect_naver_results_unknown_type_records_warning():
    block = rb.collect_naver_results(
        keyword="소방",
        search_types=["blog", "not-a-type"],
        live=False,
        config=_empty_naver_cfg(),
    )
    assert any("naver_unknown_type" in w for w in block["warnings"])
    assert "blog" in block["normalized_types"]


# ---------------------------------------------------------------------------
# YouTube collection (mock disabled)
# ---------------------------------------------------------------------------


def test_collect_youtube_results_dry_run_returns_mock_or_disabled():
    block = rb.collect_youtube_results(
        keyword="소방공사",
        max_results=3,
        with_details=True,
        live=False,
        config=_empty_yt_cfg(),
    )
    assert block["keyword"] == "소방공사"
    assert block["search"]["mode"] == "mock_or_disabled"
    assert block["search"]["items"] == []
    # with_details 요청해도 search items 없음 → details 호출 안함
    assert block["details"] is None
    assert block["success_any"] is True
    assert any("live=False" in w for w in block["warnings"])


def test_collect_youtube_results_live_with_fake_transports():
    search_payload = {
        "items": [
            {
                "id": {"videoId": "vid111"},
                "snippet": {
                    "title": "소방공사 영상 1",
                    "channelTitle": "채널A",
                    "publishedAt": "2026-04-20T10:00:00Z",
                    "description": "설명1",
                },
            },
            {
                "id": {"videoId": "vid222"},
                "snippet": {
                    "title": "소방공사 영상 2",
                    "channelTitle": "채널B",
                    "publishedAt": "2026-04-21T10:00:00Z",
                    "description": "설명2",
                },
            },
        ]
    }
    details_payload = {
        "items": [
            {
                "id": "vid111",
                "snippet": {
                    "title": "소방공사 영상 1",
                    "channelTitle": "채널A",
                    "publishedAt": "2026-04-20T10:00:00Z",
                },
                "statistics": {"viewCount": "12345", "likeCount": "111", "commentCount": "9"},
                "contentDetails": {"duration": "PT5M"},
            },
        ]
    }
    capt_search: List[Dict[str, Any]] = []
    capt_details: List[Dict[str, Any]] = []

    def search_tx(url, headers, timeout):
        capt_search.append({"url": url})
        return 200, json.dumps(search_payload)

    def details_tx(url, headers, timeout):
        capt_details.append({"url": url})
        return 200, json.dumps(details_payload)

    block = rb.collect_youtube_results(
        keyword="소방공사",
        max_results=5,
        with_details=True,
        live=True,
        config=_live_yt_cfg(),
        search_transport=search_tx,
        details_transport=details_tx,
    )
    assert block["search"]["mode"] == "live"
    assert len(block["search"]["items"]) == 2
    assert block["details"] is not None
    assert block["details"]["mode"] == "live"
    assert len(capt_search) == 1
    assert len(capt_details) == 1


# ---------------------------------------------------------------------------
# Unified item building
# ---------------------------------------------------------------------------


def _make_naver_block_with_items() -> Dict[str, Any]:
    return {
        "keyword": "소방공사",
        "requested_types": ["blog"],
        "normalized_types": ["blog"],
        "results": {
            "blog": {
                "success": True,
                "mode": "live",
                "search_type": "blog",
                "query": "소방공사",
                "items": [
                    {
                        "title": "<b>소방</b>공사 시공 가이드",
                        "link": "https://blog.example.com/1",
                        "description": "<em>핵심</em> 정리",
                        "postdate": "20260420",
                        "bloggername": "tester",
                    },
                    {
                        "title": "",
                        "link": "",
                        "description": "no title no link",
                    },
                ],
                "warnings": [],
            }
        },
        "warnings": [],
        "success_any": True,
        "failed_types": [],
    }


def _make_youtube_block_with_items() -> Dict[str, Any]:
    return {
        "keyword": "소방공사",
        "max_results": 5,
        "with_details": True,
        "search": {
            "success": True,
            "mode": "live",
            "kind": "search",
            "items": [
                {
                    "videoId": "vid111",
                    "title": "소방공사 영상 1",
                    "channelTitle": "채널A",
                    "publishedAt": "2026-04-20T10:00:00Z",
                    "description": "desc1",
                }
            ],
            "warnings": [],
        },
        "details": {
            "success": True,
            "mode": "live",
            "kind": "videos",
            "items": [
                {
                    "videoId": "vid111",
                    "title": "소방공사 영상 1",
                    "channelTitle": "채널A",
                    "publishedAt": "2026-04-20T10:00:00Z",
                    "viewCount": "12345",
                    "likeCount": "111",
                    "commentCount": "9",
                    "duration": "PT5M",
                }
            ],
            "warnings": [],
        },
        "warnings": [],
        "success_any": True,
    }


def test_build_unified_items_combines_both_platforms():
    items = rb.build_unified_items(
        _make_naver_block_with_items(),
        _make_youtube_block_with_items(),
    )
    assert len(items) == 3
    naver_titles = [it.title for it in items if it.platform == "naver"]
    assert "소방공사 시공 가이드" in naver_titles
    yt = [it for it in items if it.platform == "youtube"][0]
    assert yt.url == "https://www.youtube.com/watch?v=vid111"
    assert yt.metrics["view_count"] == 12345
    assert yt.metrics["like_count"] == 111
    assert yt.metrics["comment_count"] == 9


def test_build_unified_items_handles_one_side_disabled():
    naver = _make_naver_block_with_items()
    youtube_disabled = {
        "keyword": "소방공사",
        "search": {
            "success": True,
            "mode": "mock_or_disabled",
            "items": [],
            "warnings": ["youtube:search:live=True ... missing"],
        },
        "details": None,
        "warnings": ["youtube:search:live=True ... missing"],
        "success_any": True,
    }
    items = rb.build_unified_items(naver, youtube_disabled)
    assert all(it.platform == "naver" for it in items)
    assert len(items) == 2  # both naver items


def test_unified_item_records_risk_flags_when_missing_fields():
    items = rb.build_unified_items(_make_naver_block_with_items(), None)
    incomplete = [it for it in items if it.title == ""]
    assert len(incomplete) == 1
    assert "missing_title" in incomplete[0].risk_flags
    assert "missing_url" in incomplete[0].risk_flags


# ---------------------------------------------------------------------------
# Summary / title_terms / ideas
# ---------------------------------------------------------------------------


def test_summarize_unified_items_counts_correctly():
    items = rb.build_unified_items(
        _make_naver_block_with_items(),
        _make_youtube_block_with_items(),
    )
    s = rb.summarize_unified_items(items)
    assert s["total_items"] == 3
    assert s["naver_items"] == 2
    assert s["youtube_items"] == 1
    assert s["items_by_source_type"]["blog"] == 2
    assert s["items_by_source_type"]["youtube_video"] == 1
    assert s["items_with_risk_flag"] >= 1


def test_extract_title_terms_filters_stopwords_and_short():
    items = rb.build_unified_items(
        _make_naver_block_with_items(),
        _make_youtube_block_with_items(),
    )
    terms = rb.extract_title_terms(items, top_n=5)
    term_set = {t for t, _ in terms}
    assert "소방공사" in term_set or "소방" in term_set
    # 한 글자 단어 제외
    assert all(len(t) > 1 for t, _ in terms)


def test_build_content_ideas_uses_keywords_and_terms():
    items = rb.build_unified_items(
        _make_naver_block_with_items(),
        _make_youtube_block_with_items(),
    )
    ideas = rb.build_content_ideas(items, ["소방공사"], max_ideas=4)
    assert 1 <= len(ideas) <= 4
    assert ideas[0]["seed"] == "소방공사"
    assert ideas[0]["rank"] == 1
    assert "소방공사" in ideas[0]["title"]


def test_build_content_ideas_empty_items_returns_empty():
    assert rb.build_content_ideas([], ["foo"]) == []


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def _build_full_report() -> Dict[str, Any]:
    return rb.build_report(
        keywords=["소방공사"],
        naver_blocks=[_make_naver_block_with_items()],
        youtube_blocks=[_make_youtube_block_with_items()],
        mode="live",
        platforms_attempted=["naver", "youtube"],
        platforms_live=["naver", "youtube"],
        extra_warnings=[],
        generated_at="2026-04-26T12:00:00Z",
    )


def test_render_markdown_report_has_required_sections():
    report = _build_full_report()
    md = rb.render_markdown_report(report)
    for section in (
        "# 콘텐츠 조사 리포트",
        "## 요약",
        "## 플랫폼별 결과",
        "## 상위 노출/반응 후보",
        "## 제목 키워드 빈도",
        "## 영상 소재 후보",
        "## LTX 영상 제작 아이디어",
        "## 경고 및 제한",
        "## 다음 조치",
    ):
        assert section in md, f"missing section: {section}"


def test_write_report_files_creates_json_csv_md(tmp_path: Path):
    report = _build_full_report()
    out = rb.write_report_files(report, tmp_path, timestamp="20260426_120000")
    assert out["json"].exists()
    assert out["csv"].exists()
    assert out["md"].exists()

    payload = json.loads(out["json"].read_text(encoding="utf-8"))
    assert payload["mode"] == "live"
    assert payload["summary"]["total_items"] == 3

    rows = list(csv.DictReader(out["csv"].open("r", encoding="utf-8")))
    assert len(rows) == 3
    assert set(rb.CSV_COLUMNS).issubset(set(rows[0].keys()))


def test_write_report_files_does_not_leak_secrets(tmp_path: Path):
    report = _build_full_report()
    out = rb.write_report_files(report, tmp_path, timestamp="20260426_120000")

    raw_json = out["json"].read_text(encoding="utf-8")
    raw_csv = out["csv"].read_text(encoding="utf-8")
    raw_md = out["md"].read_text(encoding="utf-8")

    for blob in (raw_json, raw_csv, raw_md):
        assert SECRET_NAVER_ID not in blob
        assert SECRET_NAVER_SECRET not in blob
        assert SECRET_YT_KEY not in blob


def _strip_string_literals(src: str) -> str:
    """주석/문서/문자열 리터럴을 제거해 실제 코드 라인만 검사할 수 있도록 한다."""
    import io as _io
    import tokenize as _tok

    out: List[str] = []
    try:
        tokens = list(_tok.generate_tokens(_io.StringIO(src).readline))
    except Exception:
        return src
    for tok in tokens:
        if tok.type in (_tok.STRING, _tok.COMMENT, _tok.FSTRING_START, _tok.FSTRING_MIDDLE, _tok.FSTRING_END):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_module_does_not_import_browser_or_oauth():
    src = Path(rb.__file__).read_text(encoding="utf-8")
    code_only = _strip_string_literals(src)
    forbidden_idents = [
        "playwright",
        "selenium",
        "google_auth",
        "oauth2",
        "requests_oauthlib",
    ]
    for token in forbidden_idents:
        assert token not in code_only, f"forbidden ident in builder code: {token}"

    # write/comment 작업 호출 패턴은 docstring 포함 전체 src 에서도 없어야 함
    forbidden_calls = [
        "videos().insert(",
        "videos().update(",
        "videos().delete(",
        "comments().insert(",
    ]
    for call in forbidden_calls:
        assert call not in src, f"forbidden write call in builder: {call}"


def test_module_does_not_use_requests_dependency():
    src = Path(rb.__file__).read_text(encoding="utf-8")
    code_only = _strip_string_literals(src)
    assert "import requests" not in code_only
    assert "from requests" not in code_only
