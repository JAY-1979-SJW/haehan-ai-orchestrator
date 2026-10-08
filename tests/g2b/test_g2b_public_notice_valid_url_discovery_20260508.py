"""
G2B 유효 URL Discovery 스크립트 테스트

원칙:
- discovery script import side effect 없음
- content_verdict와 live_verdict 분리 확인
- 정책 준수 필드 확인
- mock/server 금지 필드 확인
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import inspect
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "g2b" / "discover_valid_public_notice_urls.py"


def _load_script():
    loader = importlib.machinery.SourceFileLoader("discover_valid_public_notice_urls", str(_SCRIPT_PATH))
    spec = importlib.util.spec_from_loader("discover_valid_public_notice_urls", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ── TC-01: import 시 side effect 없음 ────────────────────────────────────────


def test_script_import_no_side_effect():
    mod = _load_script()
    assert callable(getattr(mod, "main", None))


# ── TC-02: main() 함수 존재 ──────────────────────────────────────────────────


def test_script_has_main():
    mod = _load_script()
    assert hasattr(mod, "main")


# ── TC-03: click/type/fill/submit 호출 없음 ─────────────────────────────────


def test_script_no_click_type_fill_submit():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "page.click(" not in src
    assert "page.type(" not in src
    assert "page.fill(" not in src
    assert "page.keyboard" not in src


# ── TC-04: download 자동 실행 없음 ──────────────────────────────────────────


def test_script_no_auto_download():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "page.expect_download" not in src
    assert "download.save_as" not in src


# ── TC-05: cookie/session/token/password/otp 저장 없음 ──────────────────────


def test_script_no_secret_extraction():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    forbidden = ["cookies()", "storage_state", "page.password", "page.otp"]
    for f in forbidden:
        assert f not in src, f"금지 패턴 {f!r} 발견"


# ── TC-06: max-depth 1 강제 확인 ────────────────────────────────────────────


def test_script_max_depth_forced_one():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "max_depth = 1" in src


# ── TC-07: IS_SERVER_ENV 체크 존재 ──────────────────────────────────────────


def test_script_checks_server_env():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "IS_SERVER_ENV" in src


# ── TC-08: fail-on-mock 옵션 존재 ────────────────────────────────────────────


def test_script_has_fail_on_mock_option():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "fail_on_mock" in src


# ── TC-09: _classify_href login 경로 blocked 반환 ────────────────────────────


def test_classify_href_login_blocked():
    mod = _load_script()
    result = mod._classify_href("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do")
    assert result == "blocked"


# ── TC-10: _classify_href download 경로 blocked 반환 ─────────────────────────


def test_classify_href_download_blocked():
    mod = _load_script()
    result = mod._classify_href("https://www.g2b.go.kr/pt/file/download.do?id=1")
    assert result == "blocked"


# ── TC-11: _classify_href shop.g2b.go.kr needs_verification ─────────────────


def test_classify_href_shop_needs_verification():
    mod = _load_script()
    result = mod._classify_href("https://shop.g2b.go.kr/")
    assert result == "needs_verification"


# ── TC-12: _classify_href 허용 도메인 외부 external ──────────────────────────


def test_classify_href_external_domain():
    mod = _load_script()
    result = mod._classify_href("https://example.com/page")
    assert result == "external"


# ── TC-13: _classify_href 허용 경로 safe 반환 ────────────────────────────────


def test_classify_href_safe_allowed():
    mod = _load_script()
    result = mod._classify_href("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do")
    assert result == "safe"


# ── TC-14: content_valid_pass_candidates 리스트 구조 ─────────────────────────


def test_content_valid_pass_candidates_structure():
    # report dict 예시 생성
    candidates = [
        {
            "url": "https://www.g2b.go.kr/test",
            "title": "공고명",
            "content_verdict": "CONTENT_VALID_PASS",
            "positive_signals": [],
        }
    ]
    mod = _load_script()
    report = {
        "run_at": "2026-05-08T00:00:00+00:00",
        "actual_live_required": True,
        "mock_used": False,
        "local_agent_used": True,
        "server_browser_used": False,
        "fixture_allowed_count": 5,
        "content_valid_pass_count": 1,
        "reachable_but_not_valid_count": 4,
        "content_invalid_count": 0,
        "content_unknown_count": 0,
        "total_candidates": 1,
        "safe_candidate_count": 1,
        "blocked_candidate_count": 0,
        "needs_verification_candidate_count": 0,
        "content_valid_pass_candidates": candidates,
        "fixture_results": [],
    }
    md = mod._build_markdown_report(report, "2026-05-08T00:00:00+00:00")
    assert "CONTENT_VALID_PASS" in md or "content_valid_pass" in md.lower() or "https://www.g2b.go.kr/test" in md


# ── TC-15: _build_markdown_report 후보 없을 때 WARN 메시지 포함 ────────────────


def test_build_markdown_report_no_candidates_warn():
    mod = _load_script()
    report = {
        "run_at": "2026-05-08T00:00:00+00:00",
        "actual_live_required": True,
        "mock_used": False,
        "local_agent_used": True,
        "server_browser_used": False,
        "fixture_allowed_count": 5,
        "content_valid_pass_count": 0,
        "reachable_but_not_valid_count": 5,
        "content_invalid_count": 0,
        "content_unknown_count": 0,
        "total_candidates": 0,
        "safe_candidate_count": 0,
        "blocked_candidate_count": 0,
        "needs_verification_candidate_count": 0,
        "content_valid_pass_candidates": [],
        "fixture_results": [],
    }
    md = mod._build_markdown_report(report, "2026-05-08T00:00:00+00:00")
    assert "WARN" in md or "없음" in md


# ── TC-16: 정책 필드 모두 포함 여부 ──────────────────────────────────────────


def test_script_report_has_policy_fields():
    src = _SCRIPT_PATH.read_text(encoding="utf-8")
    policy_fields = [
        "policy_wildcard_allowed",
        "policy_login_blocked",
        "policy_download_auto_allowed",
        "policy_click_type_fill_submit_blocked",
        "policy_secret_token_saved",
        "policy_db_write",
    ]
    for f in policy_fields:
        assert f in src, f"정책 필드 {f!r} 없음"


# ── TC-17: _extract_anchors_from_page click 없음 ─────────────────────────────


def test_extract_anchors_no_click():
    mod = _load_script()
    src = inspect.getsource(mod._extract_anchors_from_page)
    assert ".click(" not in src
    assert ".submit(" not in src


# ── TC-18: REQUEST_DELAY 존재 확인 ──────────────────────────────────────────


def test_request_delay_constant_exists():
    mod = _load_script()
    assert hasattr(mod, "_REQUEST_DELAY_SEC")
    assert mod._REQUEST_DELAY_SEC > 0


# ── TC-19: _load_fixture_allowed_urls가 ALLOWED operation만 반환 ──────────────


def test_load_fixture_allowed_urls_only_allowed(tmp_path):
    import json

    fixture_data = {
        "cases": [
            {"id": "a1", "url": "https://www.g2b.go.kr/page1", "operation": "read", "expected": {"verdict": "ALLOWED"}},
            {
                "id": "a2",
                "url": "https://www.g2b.go.kr/page2",
                "operation": "navigate",
                "expected": {"verdict": "BLOCKED"},
            },
            {
                "id": "a3",
                "url": "https://www.g2b.go.kr/page3",
                "operation": "submit",
                "expected": {"verdict": "BLOCKED"},
            },
        ]
    }
    fp = tmp_path / "fixture.json"
    fp.write_text(json.dumps(fixture_data), encoding="utf-8")
    mod = _load_script()
    result = mod._load_fixture_allowed_urls(fp)
    assert len(result) == 1
    assert result[0]["id"] == "a1"


# ── TC-20: submit operation fixture는 allowed 목록에서 제외 ──────────────────


def test_submit_operation_excluded_from_allowed(tmp_path):
    import json

    fixture_data = {
        "cases": [
            {
                "id": "s1",
                "url": "https://www.g2b.go.kr/page",
                "operation": "submit",
                "expected": {"verdict": "ALLOWED"},
            },
        ]
    }
    fp = tmp_path / "fixture.json"
    fp.write_text(json.dumps(fixture_data), encoding="utf-8")
    mod = _load_script()
    result = mod._load_fixture_allowed_urls(fp)
    assert len(result) == 0
