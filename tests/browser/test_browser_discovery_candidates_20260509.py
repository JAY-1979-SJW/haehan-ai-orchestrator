"""Browser Discovery Candidates 테스트."""
from __future__ import annotations

from core.agent_runtime.runtime.site_profile.browser_discovery_candidates import (
    CANDIDATE_BUTTON,
    CANDIDATE_DESTRUCTIVE_BUTTON,
    CANDIDATE_DOWNLOAD_LINK,
    CANDIDATE_FIELD,
    CANDIDATE_FILE_INPUT,
    CANDIDATE_MENU,
    CANDIDATE_SUBMIT_BUTTON,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    build_candidate,
    classify_risk,
    fingerprint_selector,
    is_forbidden_label,
    validate_candidate_safety,
)


def test_menu_candidate_build():
    res = build_candidate(CANDIDATE_MENU, "공고검색", "link", "g2b", "/")
    assert res["ok"] is True
    assert res["candidate"]["candidate_type"] == CANDIDATE_MENU
    assert res["candidate"]["risk_hint"] == RISK_LOW


def test_field_candidate_build():
    res = build_candidate(CANDIDATE_FIELD, "검색어", "textbox", "g2b", "/search")
    assert res["ok"] is True
    assert res["candidate"]["risk_hint"] == RISK_MEDIUM


def test_button_candidate_build():
    res = build_candidate(CANDIDATE_BUTTON, "조회", "button", "g2b", "/search")
    assert res["ok"] is True


def test_destructive_button_high_risk():
    res = build_candidate(CANDIDATE_DESTRUCTIVE_BUTTON, "삭제", "button", "g2b", "/")
    assert res["ok"] is True
    assert res["candidate"]["risk_hint"] == RISK_HIGH


def test_submit_button_high_risk():
    res = build_candidate(CANDIDATE_SUBMIT_BUTTON, "제출", "button", "g2b", "/form")
    assert res["ok"] is True
    assert res["candidate"]["risk_hint"] == RISK_HIGH


def test_destructive_keyword_label_classified_high():
    assert classify_risk(CANDIDATE_BUTTON, "송금") == RISK_HIGH
    assert classify_risk(CANDIDATE_BUTTON, "전자서명") == RISK_HIGH
    assert classify_risk(CANDIDATE_BUTTON, "투찰") == RISK_HIGH


def test_forbidden_label_blocked():
    res = build_candidate(CANDIDATE_FIELD, "비밀번호", "password", "g2b", "/login")
    assert res["ok"] is False
    assert res["verdict"] == "FORBIDDEN_LABEL_BLOCKED"


def test_no_raw_html_allowed():
    bad = {"raw_html": "<input>", "candidate_type": "menu_candidate"}
    res = validate_candidate_safety(bad)
    assert res["safe"] is False


def test_no_screenshot_field():
    bad = {"screenshot": "base64...", "candidate_type": "menu_candidate"}
    assert validate_candidate_safety(bad)["safe"] is False


def test_no_cookie_field():
    bad = {"cookie": "x=y"}
    assert validate_candidate_safety(bad)["safe"] is False


def test_no_har_field():
    bad = {"har": "{}"}
    assert validate_candidate_safety(bad)["safe"] is False


def test_safe_candidate_passes():
    safe = {
        "candidate_type": "menu_candidate",
        "visible_label": "공고검색",
        "role": "link",
        "selector_fingerprint": "abc123",
    }
    assert validate_candidate_safety(safe)["safe"] is True


def test_fingerprint_deterministic():
    f1 = fingerprint_selector("button", "조회")
    f2 = fingerprint_selector("button", "조회")
    assert f1 == f2
    f3 = fingerprint_selector("button", "삭제")
    assert f1 != f3


def test_unknown_candidate_type():
    res = build_candidate("invalid_type", "x", "y", "g2b", "/")
    assert res["ok"] is False


def test_file_input_medium_risk():
    res = build_candidate(CANDIDATE_FILE_INPUT, "첨부파일", "file", "g2b", "/upload")
    assert res["ok"] is True
    assert res["candidate"]["risk_hint"] == RISK_MEDIUM


def test_download_link_low_risk():
    res = build_candidate(CANDIDATE_DOWNLOAD_LINK, "공고문 다운로드", "link", "g2b", "/notice")
    assert res["ok"] is True
    assert res["candidate"]["risk_hint"] == RISK_LOW


def test_is_forbidden_label():
    assert is_forbidden_label("비밀번호") is True
    assert is_forbidden_label("OTP 인증") is True
    assert is_forbidden_label("주민등록번호") is True
    assert is_forbidden_label("공고제목") is False
