"""tests/test_security_program_auto_resume_20260508.py"""

from core.agent_runtime.runtime.security_program.local_security_installer_runner import (
    STATUS_INSTALL_PERMISSION_REQUIRED,
    STATUS_WAITING_USER_UAC,
)
from core.agent_runtime.runtime.security_program.security_program_auto_resume import (
    FLOW_AWAIT_PERMISSION,
    FLOW_AWAIT_UAC,
    FLOW_INSTALL_COMPLETE,
    run_security_install_flow,
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

_SECURITY_PAGE = {
    "url": "https://bank.example.com/login",
    "title": "인터넷뱅킹",
    "text_content": "보안프로그램 설치가 필요합니다. 키보드보안 프로그램을 설치해주세요.",
    "buttons": ["설치"],
    "links": ["https://bank.example.com/setup.exe"],
    "form_labels": [],
    "heading_texts": ["보안 설치"],
}

_NO_SECURITY_PAGE = {
    "url": "https://example.com/",
    "title": "일반 페이지",
    "text_content": "일반 콘텐츠 페이지",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}

_COMPLETE_PAGE = {
    "url": "https://bank.example.com/",
    "title": "설치 완료",
    "text_content": "설치가 완료되었습니다.",
    "buttons": [],
    "links": [],
    "form_labels": [],
    "heading_texts": [],
}


def _assert_safe(result):
    for f in _SAFE_FIELDS:
        assert result.get(f) is False, f"{f} != False"


def test_no_security_required_returns_no_required():
    r = run_security_install_flow(
        _NO_SECURITY_PAGE,
        "공지 읽어줘",
        dry_run=True,
    )
    assert r["status"] == "NO_SECURITY_PROGRAM_REQUIRED"
    _assert_safe(r)


def test_security_detected_no_permission_await_permission():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=False,
        dry_run=True,
    )
    assert r["status"] == STATUS_INSTALL_PERMISSION_REQUIRED
    assert r["flow"] == FLOW_AWAIT_PERMISSION
    _assert_safe(r)


def test_security_with_permission_dry_run_verified():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=True,
        dry_run=True,
    )
    # exe 설치 파일은 UAC 필요 → WAITING_USER_UAC 또는 INSTALLER_VERIFIED
    assert r["status"] in ("INSTALLER_VERIFIED", STATUS_WAITING_USER_UAC)
    assert r["flow"] in (FLOW_INSTALL_COMPLETE, FLOW_AWAIT_UAC)
    _assert_safe(r)


def test_retry_ready_after_verified():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=True,
        dry_run=True,
    )
    # UAC 대기 중이거나 설치 준비 완료 상태 중 하나
    assert r["status"] in ("INSTALLER_VERIFIED", STATUS_WAITING_USER_UAC)


def test_safe_fields_always_false_no_permission():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=False,
        dry_run=True,
    )
    _assert_safe(r)


def test_safe_fields_always_false_with_permission():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=True,
        dry_run=True,
    )
    _assert_safe(r)


def test_server_browser_used_always_false():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        dry_run=True,
    )
    assert r["server_browser_used"] is False


def test_no_local_path_in_result():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=True,
        dry_run=True,
    )
    assert "local_path" not in r
    assert "full_path" not in r


def test_no_sensitive_data_in_result():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=True,
        dry_run=True,
    )
    sensitive_keys = ["password", "otp", "cookie", "session", "token", "cert_password"]
    for key in r:
        for s in sensitive_keys:
            assert s not in key.lower() or r[key] is False, f"민감 필드 발견: {key}"


def test_result_has_domain():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        has_install_permission=True,
        dry_run=True,
    )
    assert "domain" in r
    assert r["domain"] == "bank.example.com"


def test_result_has_status():
    r = run_security_install_flow(
        _SECURITY_PAGE,
        "로그인",
        dry_run=True,
    )
    assert "status" in r
