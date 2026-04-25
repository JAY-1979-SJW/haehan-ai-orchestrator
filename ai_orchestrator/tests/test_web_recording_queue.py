"""Unit tests for ai_orchestrator/video_production/recording_queue.py (F-4S-7)."""
from __future__ import annotations

import inspect
import json
import tokenize
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_orchestrator.video_production import queue_builder as qb
from ai_orchestrator.video_production import recording_queue as rq


def _sample_video_queue_items() -> List[Dict[str, Any]]:
    """F-4S-6 큐 item 형태 (세 가지 케이스: 외부 youtube, 내부 url 없음, naver_blog)."""
    return [
        {
            "queue_id": "video_001",
            "status": "draft",
            "title": "소방공사 비용 5가지 핵심 체크리스트",
            "hook": "왜 지금 '소방공사 비용 체크' 인가?",
            "duration_type": "short",
            "target_platform": "naver_blog",
            "scene_plan": [
                {"scene_no": 1, "purpose": "문제 제기", "visual_direction": "비용 도식", "caption": "비용 핵심", "narration": "소방공사 비용을 5가지로 정리"},
                {"scene_no": 2, "purpose": "핵심 정보 전달", "visual_direction": "체크리스트 카드", "caption": "체크리스트", "narration": "5가지 항목 정리"},
                {"scene_no": 3, "purpose": "CTA / 마무리", "visual_direction": "자료 다운로드", "caption": "자료", "narration": "자료 다운로드 안내"},
            ],
            "subtitle_points": ["핵심 메시지: 소방공사 비용", "키워드 강조: 소방공사"],
            "source_basis": [
                {"platform": "naver", "source_type": "blog", "url": "https://example.com/blog/firework-cost", "title": "소방공사 비용"}
            ],
            "ltx_prompt": "(...)",
            "risk_notes": ["read-only 분석 결과 기반"],
            "review_required": True,
        },
        {
            "queue_id": "video_002",
            "status": "draft",
            "title": "스마트팩토리 #shorts 30초 핵심",
            "hook": "왜 지금 '스마트팩토리' 인가?",
            "duration_type": "short",
            "target_platform": "youtube_short",
            "scene_plan": [
                {"scene_no": 1, "purpose": "문제 제기", "visual_direction": "공장 b-roll", "caption": "공장", "narration": "왜 지금?"}
            ],
            "subtitle_points": ["핵심 메시지: 스마트팩토리"],
            "source_basis": [
                {"platform": "youtube", "source_type": "youtube_video", "url": "https://www.youtube.com/watch?v=fixture555", "title": "스마트팩토리 30초"}
            ],
            "ltx_prompt": "(...)",
            "risk_notes": [],
            "review_required": True,
        },
        {
            "queue_id": "video_003",
            "status": "draft",
            "title": "[법령 안내] 소방시설 기준 개정안 시행",
            "hook": "왜 지금 '법령 개정' 인가?",
            "duration_type": "long",
            "target_platform": "naver_blog",
            "scene_plan": [
                {"scene_no": 1, "purpose": "오프닝 / 후크", "visual_direction": "법령 도식", "caption": "법령", "narration": "법령 개요"},
                {"scene_no": 2, "purpose": "문제/배경 설명", "visual_direction": "타임라인", "caption": "타임라인", "narration": "변경 내용"},
                {"scene_no": 3, "purpose": "핵심 정보 1", "visual_direction": "조항 카드", "caption": "조항 1", "narration": "핵심 1"},
                {"scene_no": 4, "purpose": "핵심 정보 2", "visual_direction": "조항 카드", "caption": "조항 2", "narration": "핵심 2"},
                {"scene_no": 5, "purpose": "정리 / CTA", "visual_direction": "요약", "caption": "요약", "narration": "정리"},
            ],
            "subtitle_points": ["핵심 메시지: 소방시설 기준 개정"],
            "source_basis": [
                {"platform": "naver", "source_type": "news", "url": "https://example.com/news/firework-law-update", "title": "법령 개정"}
            ],
            "ltx_prompt": "(...)",
            "risk_notes": ["법령/단가/안전 표현 감지 — 최종 검수 필요"],
            "review_required": True,
        },
    ]


def _sample_video_queue_dict() -> Dict[str, Any]:
    return {
        "generated_at": "2026-04-26T01:00:00Z",
        "queue_count": 3,
        "queue": _sample_video_queue_items(),
        "notes": ["F-4S-6 LTX 영상 제작 큐 PoC"],
    }


# ---------------------------------------------------------------------------
# extract_recording_candidates / load_video_queue
# ---------------------------------------------------------------------------


def test_extract_recording_candidates_from_queue_dict():
    items = rq.extract_recording_candidates(_sample_video_queue_dict())
    assert len(items) == 3
    assert items[0]["queue_id"] == "video_001"


def test_extract_recording_candidates_from_brief_list():
    briefs = [{"title": "x", "scene_plan": [], "source_basis": []}]
    items = rq.extract_recording_candidates(briefs)
    assert len(items) == 1


def test_extract_recording_candidates_from_report_briefs():
    report_like = {"ltx_video_briefs": [{"title": "y", "scene_plan": [], "source_basis": []}]}
    items = rq.extract_recording_candidates(report_like)
    assert len(items) == 1


def test_extract_recording_candidates_empty():
    assert rq.extract_recording_candidates(None) == []
    assert rq.extract_recording_candidates({}) == []
    assert rq.extract_recording_candidates({"other": 1}) == []


def test_load_video_queue_roundtrip(tmp_path: Path):
    p = tmp_path / "video_queue.json"
    p.write_text(json.dumps(_sample_video_queue_dict(), ensure_ascii=False), encoding="utf-8")
    loaded = rq.load_video_queue(p)
    assert loaded["queue_count"] == 3


# ---------------------------------------------------------------------------
# normalize_recording_target
# ---------------------------------------------------------------------------


def test_normalize_target_uses_explicit_target_url():
    info = rq.normalize_recording_target(
        {"target_url": "https://internal.example/page", "source_basis": []}
    )
    assert info["target_url"] == "https://internal.example/page"
    assert not any("missing" in w for w in info["warnings"])


def test_normalize_target_falls_back_to_base_url():
    info = rq.normalize_recording_target(
        {"target_url": "", "source_basis": []},
        default_base_url="http://localhost:3000",
    )
    assert info["target_url"] == "http://localhost:3000"


def test_normalize_target_missing_url_warns():
    info = rq.normalize_recording_target({"target_url": "", "source_basis": []})
    assert info["target_url"] is None
    assert any("target_url_missing" in w for w in info["warnings"])


def test_normalize_target_external_platform_warns():
    info = rq.normalize_recording_target(
        {"target_url": "", "source_basis": []},
        default_base_url="https://www.youtube.com/watch?v=abc",
    )
    assert info["target_url"] == "https://www.youtube.com/watch?v=abc"
    assert any("external_target" in w for w in info["warnings"])


def test_normalize_target_login_required_warns():
    info = rq.normalize_recording_target(
        {"target_url": "https://internal.example/login?next=/admin", "source_basis": []}
    )
    assert any("login_required" in w for w in info["warnings"])


def test_normalize_target_invalid_base_url_warns():
    info = rq.normalize_recording_target(
        {"target_url": "", "source_basis": []},
        default_base_url="not a url",
    )
    assert info["target_url"] is None
    assert any("invalid_base_url" in w for w in info["warnings"])


# ---------------------------------------------------------------------------
# build_recording_queue / steps
# ---------------------------------------------------------------------------


def test_build_recording_queue_basic_shape():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        viewport="desktop",
        max_items=5,
    )
    assert len(items) == 3
    item = items[0]
    expected_keys = {
        "recording_id", "source_queue_id", "status", "title", "target_url",
        "viewport", "duration_seconds", "recording_steps",
        "subtitle_points", "narration_points", "editing_notes",
        "risk_notes", "review_required",
    }
    assert expected_keys <= set(item.keys())
    assert item["recording_id"] == "recording_001"
    assert item["source_queue_id"] == "video_001"
    assert item["status"] == "draft"


def test_build_recording_queue_respects_max_items():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        max_items=2,
    )
    assert len(items) == 2
    assert items[0]["recording_id"] == "recording_001"
    assert items[1]["recording_id"] == "recording_002"


def test_build_recording_queue_skips_no_title():
    bad = [{"title": "", "scene_plan": [], "source_basis": []}]
    out = rq.build_recording_queue({"queue": bad}, max_items=5)
    assert out == []


def test_viewport_desktop_dimensions():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        viewport="desktop",
    )
    assert items[0]["viewport"] == {"name": "desktop", "width": 1440, "height": 900}


def test_viewport_mobile_dimensions():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        viewport="mobile",
    )
    assert items[0]["viewport"] == {"name": "mobile", "width": 390, "height": 844}


def test_viewport_wide_dimensions():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        viewport="wide",
    )
    assert items[0]["viewport"] == {"name": "wide", "width": 1920, "height": 1080}


def test_viewport_unknown_falls_back_desktop():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        viewport="ultrawide_4k",
    )
    assert items[0]["viewport"]["name"] == "desktop"


def test_recording_steps_only_allowed_types():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        max_items=5,
    )
    for item in items:
        for step in item["recording_steps"]:
            assert step["type"] in rq.ALLOWED_STEP_TYPES, (
                f"unexpected step type: {step['type']}"
            )
            assert step["type"] not in rq.FORBIDDEN_STEP_TYPES


def test_recording_steps_have_open_url_first():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
    )
    first_step = items[0]["recording_steps"][0]
    assert first_step["type"] == "open_url"
    assert first_step["url"] == "http://localhost:3000"


def test_recording_steps_have_capture_scene_for_each_scene():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
    )
    long_item = next(it for it in items if it["source_queue_id"] == "video_003")
    capture_steps = [s for s in long_item["recording_steps"] if s["type"] == "capture_scene"]
    assert len(capture_steps) == 5


def test_recording_steps_overlay_caption_last():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
    )
    assert items[0]["recording_steps"][-1]["type"] == "overlay_caption"


def test_external_youtube_target_warns_in_risk_notes():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url=None,
        max_items=5,
    )
    yt_item = next(it for it in items if it["source_queue_id"] == "video_002")
    risks = " ".join(yt_item["risk_notes"])
    # 외부 플랫폼 경고 또는 target_url_missing 경고 중 하나는 반드시 존재
    assert ("external_target" in risks) or ("target_url_missing" in risks)


def test_missing_target_url_when_no_base_and_external_only():
    queue = {
        "queue": [
            {
                "queue_id": "video_x",
                "title": "외부만 있는 케이스",
                "duration_type": "short",
                "scene_plan": [{"scene_no": 1, "purpose": "p", "visual_direction": "v", "caption": "c", "narration": "n"}],
                "subtitle_points": [],
                "source_basis": [],
                "risk_notes": [],
                "review_required": True,
            }
        ]
    }
    items = rq.build_recording_queue(queue, default_base_url=None, max_items=1)
    assert items[0]["target_url"] is None
    assert any("target_url_missing" in w for w in items[0]["risk_notes"])


def test_review_required_always_true_for_poc():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        max_items=3,
    )
    assert all(item["review_required"] is True for item in items)


def test_subtitle_and_narration_present():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
    )
    item = items[0]
    assert item["subtitle_points"]
    assert item["narration_points"]
    assert item["editing_notes"]


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def test_render_markdown_contains_titles_and_constraints():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
    )
    md = rq.render_recording_queue_markdown(items)
    assert "웹 자동녹화 큐" in md
    assert "허용 step" in md
    assert "금지 step" in md
    for it in items:
        assert it["title"] in md


def test_render_markdown_empty():
    md = rq.render_recording_queue_markdown([])
    assert "큐 비어 있음" in md


def test_write_recording_queue_files(tmp_path: Path):
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        max_items=2,
    )
    files = rq.write_recording_queue_files(items, tmp_path, timestamp="20260426_010101")
    assert files["json"].exists()
    assert files["md"].exists()
    payload = json.loads(files["json"].read_text(encoding="utf-8"))
    assert payload["recording_count"] == 2
    assert "allowed_step_types" in payload
    assert "forbidden_step_types" in payload
    assert "click" in payload["forbidden_step_types"]


# ---------------------------------------------------------------------------
# Forbidden step / security boundary checks
# ---------------------------------------------------------------------------


def test_no_click_fill_type_press_steps_in_any_item():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        max_items=5,
    )
    serialized = json.dumps(items, ensure_ascii=False)
    for forbidden_type_token in (
        '"type": "click"',
        '"type": "fill"',
        '"type": "type"',
        '"type": "press"',
        '"type": "submit"',
        '"type": "upload"',
        '"type": "login"',
    ):
        assert forbidden_type_token not in serialized, (
            f"forbidden step type appeared in queue: {forbidden_type_token}"
        )


def _strip_comments_and_strings(src: str) -> str:
    out_tokens: List[str] = []
    try:
        for tok in tokenize.generate_tokens(StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING:
                out_tokens.append('""')
                continue
            out_tokens.append(tok.string)
    except tokenize.TokenizeError:
        return src
    return " ".join(out_tokens)


def _module_source() -> str:
    src_path = Path(inspect.getsourcefile(rq))  # type: ignore[arg-type]
    return src_path.read_text(encoding="utf-8")


def test_module_does_not_import_browser_or_oauth():
    src_no_strings = _strip_comments_and_strings(_module_source())
    forbidden_imports = (
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "import puppeteer",
        "from puppeteer",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    )
    for needle in forbidden_imports:
        assert needle not in src_no_strings, f"forbidden import found: {needle}"


def test_module_has_no_runtime_browser_or_login_calls():
    src_no_strings = _strip_comments_and_strings(_module_source())
    forbidden = (
        "page.click(", "page.fill(", "page.type(", "page.press(",
        "page.goto(", ".launch(", ".new_context(", ".storage_state(",
        "context.cookies(", ".upload(", ".publish(", "ltx_client.",
    )
    for needle in forbidden:
        assert needle not in src_no_strings, f"forbidden runtime call: {needle}"


def test_queue_does_not_inject_secret_like_tokens():
    items = rq.build_recording_queue(
        _sample_video_queue_dict(),
        default_base_url="http://localhost:3000",
        max_items=5,
    )
    serialized = json.dumps(items, ensure_ascii=False)
    for tok in ("sk-", "AIza", "Bearer ", "Authorization:", "Cookie:", "Set-Cookie:"):
        assert tok not in serialized, f"unexpected secret-like token injected: {tok}"


def test_e2e_from_video_queue_to_recording():
    """F-4S-6 build_video_queue 출력 → F-4S-7 build_recording_queue 입력 의 통합 흐름 검증."""
    sample_briefs = [
        {
            "title": "통합 흐름 테스트 제목",
            "hook": "hook",
            "scene_ideas": ["오프닝 hook"],
            "subtitle_points": ["핵심"],
            "source_basis": [{"platform": "naver", "source_type": "blog", "url": "https://e.com/x", "title": "t"}],
            "target_platform": "naver_blog",
            "risk_notes": [],
            "score": 1.0,
        }
    ]
    video_queue = qb.build_video_queue(sample_briefs, max_items=1)
    recording_items = rq.build_recording_queue(
        video_queue,
        default_base_url="http://localhost:3000",
        max_items=1,
    )
    assert len(recording_items) == 1
    rec = recording_items[0]
    assert rec["source_queue_id"] == "video_001"
    assert rec["target_url"] == "http://localhost:3000"
    assert rec["recording_steps"][0]["type"] == "open_url"
