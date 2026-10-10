"""tests/test_security_program_install_completion_detector_20260508.py"""

from core.agent_runtime.runtime.security_program.security_program_install_completion_detector import (
    DETECTION_HEADLESS_REQUIRES_HEADED,
    DETECTION_INSTALL_COMPLETED,
    DETECTION_INSTALL_NOT_DETECTED,
    DETECTION_PARTIAL_RESOLVED,
    detect_install_completion,
    is_retry_ready,
)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]

_BEFORE = {
    "url": "https://bank.example.com/",
    "title": "보안프로그램 설치 안내",
    "text_content": "보안프로그램 설치가 필요합니다. 키보드보안 설치하세요.",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_AFTER_CLEAN = {
    "url": "https://bank.example.com/",
    "title": "정상 페이지",
    "text_content": "환영합니다",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_AFTER_PARTIAL = {
    "url": "https://bank.example.com/",
    "title": "보안프로그램",
    "text_content": "키보드보안 프로그램을 설치하세요.",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_AFTER_SAME = {
    "url": "https://bank.example.com/",
    "title": "보안프로그램 설치 안내",
    "text_content": "보안프로그램 설치가 필요합니다. 키보드보안 설치하세요.",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}


def test_complete_install_detected():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=True)
    assert r["status"] == DETECTION_INSTALL_COMPLETED
    assert r["install_detected"] is True


def test_install_not_detected():
    r = detect_install_completion(_BEFORE, _AFTER_SAME, headed=True)
    assert r["status"] == DETECTION_INSTALL_NOT_DETECTED
    assert r["install_detected"] is False


def test_partial_resolved():
    r = detect_install_completion(_BEFORE, _AFTER_PARTIAL, headed=True)
    assert r["status"] == DETECTION_PARTIAL_RESOLVED
    assert r["install_detected"] is False


def test_headless_returns_special_status():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=False)
    assert r["status"] == DETECTION_HEADLESS_REQUIRES_HEADED
    assert r["install_detected"] is False


def test_signals_resolved_listed():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=True)
    assert "SECURITY_PROGRAM_REQUIRED" in r["signals_resolved"]


def test_is_retry_ready_true():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=True)
    assert is_retry_ready(r) is True


def test_is_retry_ready_false_for_partial():
    r = detect_install_completion(_BEFORE, _AFTER_PARTIAL, headed=True)
    assert is_retry_ready(r) is False


def test_is_retry_ready_false_for_headless():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=False)
    assert is_retry_ready(r) is False


def test_safe_fields_always_false():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=True)
    for f in _SAFE_FIELDS:
        assert r.get(f) is False


def test_no_local_path_in_result():
    r = detect_install_completion(_BEFORE, _AFTER_CLEAN, headed=True)
    for key in r:
        assert "local_path" not in key.lower()
        assert "full_path" not in key.lower()
