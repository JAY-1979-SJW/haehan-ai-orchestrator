"""Unit tests for ai_orchestrator/video_production/queue_builder.py (F-4S-6)."""
from __future__ import annotations

import inspect
import json
import re
import tokenize
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ai_orchestrator.video_production import queue_builder as qb


def _sample_briefs() -> List[Dict[str, Any]]:
    return [
        {
            "title": "소방공사 비용 5가지 핵심 체크리스트",
            "hook": "왜 지금 '소방공사 비용 체크' 인가?",
            "scene_ideas": [
                "오프닝 — '소방공사 비용 체크' 한 줄 hook",
                "핵심 포인트 3가지 자막 강조",
                "마무리 CTA — 자료 다운로드 안내",
            ],
            "subtitle_points": [
                "핵심 메시지: 소방공사 비용 5가지 핵심 체크리스트",
                "보조 요약: 견적 받기 전 확인 5항목",
                "키워드 강조: 소방공사",
            ],
            "source_basis": [
                {
                    "platform": "naver",
                    "source_type": "blog",
                    "url": "https://example.com/blog/firework-cost",
                    "title": "소방공사 비용 5가지 핵심 체크리스트",
                }
            ],
            "target_platform": "naver_blog",
            "risk_notes": ["read-only 분석 결과 기반"],
            "score": 5.5,
        },
        {
            "title": "소방공사 어떻게 하나요? 초보 사장님을 위한 가이드",
            "hook": "왜 지금 '소방공사 어떻게 하나요?' 인가?",
            "scene_ideas": ["오프닝 hook", "핵심 3가지 자막", "마무리 안내"],
            "subtitle_points": ["핵심 메시지: 소방공사 어떻게"],
            "source_basis": [
                {
                    "platform": "youtube",
                    "source_type": "youtube_video",
                    "url": "https://www.youtube.com/watch?v=fixture111",
                    "title": "소방공사 어떻게 하나요?",
                }
            ],
            "target_platform": "youtube_long",
            "risk_notes": [],
            "score": 7.2,
        },
        {
            "title": "스마트팩토리 #shorts 30초 핵심",
            "hook": "왜 지금 '스마트팩토리 30초 핵심' 인가?",
            "scene_ideas": ["오프닝 hook", "핵심 메시지 강조"],
            "subtitle_points": ["핵심 메시지: 스마트팩토리 30초 핵심"],
            "source_basis": [
                {
                    "platform": "youtube",
                    "source_type": "youtube_video",
                    "url": "https://www.youtube.com/watch?v=fixture555",
                    "title": "스마트팩토리 #shorts",
                }
            ],
            "target_platform": "youtube_short",
            "risk_notes": [],
            "score": 9.1,
        },
        {
            "title": "[법령 안내] 소방시설 기준 개정안 시행",
            "hook": "왜 지금 '소방시설 기준 개정안' 인가?",
            "scene_ideas": ["오프닝 — 법령 변경 요지"],
            "subtitle_points": ["핵심 메시지: 소방시설 기준 개정"],
            "source_basis": [
                {
                    "platform": "naver",
                    "source_type": "news",
                    "url": "https://example.com/news/firework-law-update",
                    "title": "소방시설 기준 개정안 시행",
                }
            ],
            "target_platform": "naver_blog",
            "risk_notes": [],
            "score": 4.0,
        },
    ]


# ---------------------------------------------------------------------------
# extract_ltx_briefs / load_content_report
# ---------------------------------------------------------------------------


def test_extract_ltx_briefs_from_report_dict():
    briefs = _sample_briefs()
    report = {"ltx_video_briefs": briefs, "summary": {"total_items": 4}}
    out = qb.extract_ltx_briefs(report)
    assert out == briefs


def test_extract_ltx_briefs_from_brief_list():
    briefs = _sample_briefs()
    out = qb.extract_ltx_briefs(briefs)
    assert out == briefs


def test_extract_ltx_briefs_empty_when_missing():
    assert qb.extract_ltx_briefs({}) == []
    assert qb.extract_ltx_briefs({"other": 1}) == []
    assert qb.extract_ltx_briefs(None) == []


def test_load_content_report_roundtrip(tmp_path: Path):
    report = {"ltx_video_briefs": _sample_briefs(), "mode": "fixture"}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    loaded = qb.load_content_report(path)
    assert loaded["mode"] == "fixture"
    assert qb.extract_ltx_briefs(loaded) == _sample_briefs()


# ---------------------------------------------------------------------------
# build_video_queue / scene_plan / ltx_prompt
# ---------------------------------------------------------------------------


def test_build_video_queue_basic_shape():
    queue = qb.build_video_queue(_sample_briefs(), max_items=5)
    assert len(queue) == 4
    item = queue[0]
    expected_keys = {
        "queue_id", "status", "title", "hook", "duration_type",
        "target_platform", "scene_plan", "subtitle_points",
        "source_basis", "ltx_prompt", "risk_notes", "review_required",
    }
    assert expected_keys <= set(item.keys())
    assert item["queue_id"] == "video_001"
    assert item["status"] == "draft"
    assert item["target_platform"] in qb.VALID_TARGET_PLATFORMS
    assert item["duration_type"] in qb.VALID_DURATION_TYPES


def test_build_video_queue_respects_max_items():
    queue = qb.build_video_queue(_sample_briefs(), max_items=2)
    assert len(queue) == 2
    assert queue[0]["queue_id"] == "video_001"
    assert queue[1]["queue_id"] == "video_002"


def test_build_video_queue_skips_briefs_without_title():
    briefs = [{"title": "", "target_platform": "naver_blog"}, _sample_briefs()[0]]
    queue = qb.build_video_queue(briefs, max_items=5)
    assert len(queue) == 1
    assert queue[0]["title"]


def test_duration_inferred_from_target_platform():
    briefs = _sample_briefs()
    queue = qb.build_video_queue(briefs, default_duration_type="long", max_items=5)
    by_platform = {q["target_platform"]: q for q in queue}
    assert by_platform["youtube_short"]["duration_type"] == "short"
    assert by_platform["youtube_long"]["duration_type"] == "long"
    # 비유튜브 플랫폼은 default_duration_type 따름
    assert by_platform["naver_blog"]["duration_type"] == "long"


def test_duration_default_is_short_when_invalid():
    briefs = [_sample_briefs()[0]]  # naver_blog
    queue = qb.build_video_queue(briefs, default_duration_type="invalid", max_items=1)
    assert queue[0]["duration_type"] == "short"


def test_scene_plan_short_has_three_scenes():
    briefs = [_sample_briefs()[2]]  # youtube_short
    queue = qb.build_video_queue(briefs, max_items=1)
    plan = queue[0]["scene_plan"]
    assert len(plan) == 3
    assert plan[0]["scene_no"] == 1
    assert plan[0]["purpose"]
    assert plan[0]["caption"]


def test_scene_plan_long_has_five_scenes():
    briefs = [_sample_briefs()[1]]  # youtube_long
    queue = qb.build_video_queue(briefs, max_items=1)
    plan = queue[0]["scene_plan"]
    assert len(plan) == 5
    purposes = [sc["purpose"] for sc in plan]
    assert "오프닝 / 후크" in purposes
    assert "정리 / CTA" in purposes


def test_ltx_prompt_contains_title_and_constraints():
    queue = qb.build_video_queue(_sample_briefs(), max_items=1)
    prompt = queue[0]["ltx_prompt"]
    assert isinstance(prompt, str) and prompt
    assert "LTX 영상 제작 지시서" in prompt
    assert queue[0]["title"] in prompt
    assert "실제 LTX 호출" in prompt
    # 실제 호출 명령(curl/import 등) 미포함
    assert "curl" not in prompt.lower()
    assert "import " not in prompt
    assert "api_key" not in prompt.lower()


def test_ltx_prompt_built_via_build_ltx_prompt():
    item = {
        "title": "테스트 제목",
        "hook": "왜 지금?",
        "duration_type": "short",
        "target_platform": "youtube_short",
        "subtitle_points": ["포인트 1", "포인트 2"],
        "scene_plan": [
            {"scene_no": 1, "purpose": "문제 제기", "visual_direction": "도식", "caption": "cap", "narration": "n"}
        ],
        "source_basis": [{"platform": "naver", "source_type": "blog", "url": "u", "title": "t"}],
    }
    prompt = qb.build_ltx_prompt(item)
    assert "테스트 제목" in prompt
    assert "youtube_short" in prompt
    assert "포인트 1" in prompt


# ---------------------------------------------------------------------------
# Risk notes / review_required
# ---------------------------------------------------------------------------


def test_risk_notes_flag_law_keyword():
    briefs = [_sample_briefs()[3]]  # 법령 안내
    queue = qb.build_video_queue(briefs, max_items=1)
    risk_text = " ".join(queue[0]["risk_notes"])
    assert "최종 검수 필요" in risk_text
    assert queue[0]["review_required"] is True


def test_risk_notes_flag_cost_keyword():
    briefs = [_sample_briefs()[0]]  # 비용 체크리스트
    queue = qb.build_video_queue(briefs, max_items=1)
    risk_text = " ".join(queue[0]["risk_notes"])
    assert "최종 검수 필요" in risk_text


def test_risk_notes_flag_forbidden_tone():
    briefs = [
        {
            "title": "100% 보장하는 최고의 서비스",
            "hook": "최고의 솔루션",
            "scene_ideas": [],
            "subtitle_points": [],
            "source_basis": [{"platform": "naver", "source_type": "blog", "url": "https://e.com/x", "title": "t"}],
            "target_platform": "naver_blog",
            "risk_notes": [],
            "score": 1.0,
        }
    ]
    queue = qb.build_video_queue(briefs, max_items=1)
    risk_text = " ".join(queue[0]["risk_notes"])
    assert "표현 순화 필요" in risk_text


def test_risk_notes_flag_missing_source():
    briefs = [
        {
            "title": "출처 없는 제목",
            "hook": "hook",
            "scene_ideas": [],
            "subtitle_points": [],
            "source_basis": [],
            "target_platform": "naver_blog",
            "risk_notes": [],
            "score": 0.0,
        }
    ]
    queue = qb.build_video_queue(briefs, max_items=1)
    risk_text = " ".join(queue[0]["risk_notes"])
    assert "출처 누락" in risk_text


def test_review_required_always_true_for_poc():
    queue = qb.build_video_queue(_sample_briefs(), max_items=4)
    assert all(item["review_required"] is True for item in queue)


# ---------------------------------------------------------------------------
# normalize_video_brief
# ---------------------------------------------------------------------------


def test_normalize_video_brief_handles_missing_fields():
    norm = qb.normalize_video_brief({"title": "  hello  "})
    assert norm["title"] == "hello"
    assert norm["target_platform"] in qb.VALID_TARGET_PLATFORMS
    assert norm["scene_ideas"] == []
    assert norm["source_basis"] == []


def test_normalize_video_brief_coerces_invalid_target_platform():
    norm = qb.normalize_video_brief({"title": "x", "target_platform": "tiktok"})
    assert norm["target_platform"] == "naver_blog"


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def test_render_video_queue_markdown_contains_titles():
    queue = qb.build_video_queue(_sample_briefs(), max_items=4)
    md = qb.render_video_queue_markdown(queue)
    assert "LTX 영상 제작 큐" in md
    for item in queue:
        assert item["title"] in md
    assert "video_001" in md


def test_render_video_queue_markdown_empty_queue():
    md = qb.render_video_queue_markdown([])
    assert "큐 비어 있음" in md


def test_write_video_queue_files_creates_json_and_md(tmp_path: Path):
    queue = qb.build_video_queue(_sample_briefs(), max_items=2)
    files = qb.write_video_queue_files(queue, tmp_path, timestamp="20260426_010101")
    assert files["json"].exists()
    assert files["md"].exists()
    payload = json.loads(files["json"].read_text(encoding="utf-8"))
    assert payload["queue_count"] == 2
    assert payload["queue"][0]["queue_id"] == "video_001"
    md_text = files["md"].read_text(encoding="utf-8")
    assert "video_001" in md_text


# ---------------------------------------------------------------------------
# Security / boundary checks
# ---------------------------------------------------------------------------


def _builder_source() -> str:
    src_path = Path(inspect.getsourcefile(qb))  # type: ignore[arg-type]
    return src_path.read_text(encoding="utf-8")


def _strip_comments_and_strings(src: str) -> str:
    out_tokens: List[str] = []
    try:
        for tok in tokenize.generate_tokens(StringIO(src).readline):
            tok_type = tok.type
            tok_str = tok.string
            if tok_type == tokenize.COMMENT:
                continue
            if tok_type == tokenize.STRING:
                out_tokens.append('""')
                continue
            out_tokens.append(tok_str)
    except tokenize.TokenizeError:
        return src
    return " ".join(out_tokens)


def test_builder_does_not_import_browser_or_oauth():
    src_no_strings = _strip_comments_and_strings(_builder_source())
    forbidden_imports = (
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    )
    for needle in forbidden_imports:
        assert needle not in src_no_strings, f"forbidden import found: {needle}"


def test_builder_has_no_oauth_or_write_calls():
    src = _builder_source()
    forbidden_runtime = (
        "oauth2",
        "OAuth2",
        "client_secret=",
        "access_token=",
    )
    for needle in forbidden_runtime:
        assert needle not in src, f"forbidden token in source: {needle}"


def test_builder_has_no_real_ltx_call():
    src_no_strings = _strip_comments_and_strings(_builder_source())
    forbidden = ("ltx.run(", "ltx_client.", "render_video(", ".upload(", ".publish(")
    for needle in forbidden:
        assert needle not in src_no_strings, f"forbidden runtime call: {needle}"


def test_queue_does_not_leak_secret_strings():
    secret = "should-not-leak-in-queue"
    briefs = [
        {
            "title": f"제목 {secret}",
            "hook": "hook",
            "scene_ideas": [],
            "subtitle_points": [secret],
            "source_basis": [{"platform": "naver", "source_type": "blog", "url": "https://e.com", "title": "t"}],
            "target_platform": "naver_blog",
            "risk_notes": [],
            "score": 0.0,
        }
    ]
    queue = qb.build_video_queue(briefs, max_items=1)
    serialized = json.dumps(queue, ensure_ascii=False)
    # secret 자체는 입력에 포함되었으므로 큐에 들어가는 것은 정상.
    # 검증 포인트: 모듈 자체가 비밀(sk-, AIza, NaverClientSecret 등)을 자동 주입하지 않는다.
    forbidden_injected = ("sk-", "AIza", "Bearer ", "Authorization:")
    for tok in forbidden_injected:
        assert tok not in serialized, f"unexpected secret-like token injected: {tok}"


def test_pkg_init_documents_constraints():
    init_path = Path(qb.__file__).parent / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    for needle in ("OAuth", "playwright", "write 액션", "LTX API"):
        assert needle in text or needle.lower() in text.lower()
