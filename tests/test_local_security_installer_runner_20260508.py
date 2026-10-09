"""tests/test_local_security_installer_runner_20260508.py"""

from core.agent_runtime.runtime.security_program.local_security_installer_runner import (
    GRADE_BLOCKED,
    STATUS_INSTALL_COMPLETED,
    STATUS_INSTALL_FAILED,
    STATUS_INSTALL_PERMISSION_REQUIRED,
    STATUS_INSTALL_RUNNING,
    STATUS_RESTART_BROWSER_REQUIRED,
    STATUS_RETRY_ORIGINAL_TASK_READY,
    STATUS_WAITING_USER_UAC,
    check_action_allowed,
    check_install_completed,
    get_retry_ready_result,
    prepare_install,
)

_CANDIDATE = {
    "url": "https://bank.example.com/setup.exe",
    "filename": "setup.exe",
    "extension": ".exe",
    "allowed": True,
    "block_reason": None,
    "needs_extra_approval": False,
    "requires_permission": True,
    "source_host": "bank.example.com",
}

_BLOCKED_CANDIDATE = {
    **_CANDIDATE,
    "allowed": False,
    "block_reason": "차단 확장자: .bat",
    "filename": "install.bat",
}


def test_blocked_action_returns_blocked():
    r = check_action_allowed("bypass_uac")
    assert r["allowed"] is False
    assert r["grade"] == GRADE_BLOCKED


def test_bypass_security_program_blocked():
    r = check_action_allowed("bypass_security_program")
    assert r["allowed"] is False


def test_disable_security_module_blocked():
    r = check_action_allowed("disable_security_module")
    assert r["allowed"] is False


def test_kill_security_process_blocked():
    r = check_action_allowed("kill_security_process")
    assert r["allowed"] is False


def test_auto_uac_approval_blocked():
    r = check_action_allowed("auto_uac_approval")
    assert r["allowed"] is False


def test_silent_install_auto_blocked():
    r = check_action_allowed("silent_install_auto")
    assert r["allowed"] is False


def test_read_page_allowed():
    r = check_action_allowed("read_page")
    assert r["allowed"] is True


def test_no_permission_returns_permission_required():
    r = prepare_install(_CANDIDATE, has_permission=False)
    assert r["status"] == STATUS_INSTALL_PERMISSION_REQUIRED
    assert r["executable"] is False
    assert r["server_browser_used"] is False


def test_with_permission_uac_required():
    policy = {"requires_uac": True}
    r = prepare_install(_CANDIDATE, has_permission=True, policy_result=policy)
    assert r["status"] == STATUS_WAITING_USER_UAC
    assert r["requires_uac"] is True


def test_with_permission_no_uac_verified():
    policy = {"requires_uac": False}
    r = prepare_install(_CANDIDATE, has_permission=True, policy_result=policy)
    assert r["status"] == "INSTALLER_VERIFIED"
    assert r["executable"] is True


def test_blocked_candidate_returns_failed():
    r = prepare_install(_BLOCKED_CANDIDATE, has_permission=True)
    assert r["status"] == STATUS_INSTALL_FAILED
    assert r["executable"] is False


def test_check_install_completed_true():
    page = {
        "url": "https://bank.example.com/",
        "title": "완료",
        "text_content": "설치가 완료되었습니다.",
        "buttons": [],
        "links": [],
        "form_labels": [],
        "heading_texts": [],
    }
    r = check_install_completed(page)
    assert r["install_completed"] is True
    assert r["status"] == STATUS_INSTALL_COMPLETED


def test_check_install_running():
    page = {
        "url": "https://bank.example.com/",
        "title": "설치 중",
        "text_content": "설치 중입니다.",
        "buttons": [],
        "links": [],
        "form_labels": [],
        "heading_texts": [],
    }
    r = check_install_completed(page)
    assert r["install_completed"] is False
    assert r["status"] == STATUS_INSTALL_RUNNING


def test_restart_browser_required():
    page = {
        "url": "https://bank.example.com/",
        "title": "완료",
        "text_content": "설치 완료 브라우저 재시작 후 이용해주세요.",
        "buttons": [],
        "links": [],
        "form_labels": [],
        "heading_texts": [],
    }
    r = check_install_completed(page)
    assert r["restart_browser_required"] is True
    assert r["status"] == STATUS_RESTART_BROWSER_REQUIRED


def test_get_retry_ready_result():
    r = get_retry_ready_result("task-123")
    assert r["status"] == STATUS_RETRY_ORIGINAL_TASK_READY
    assert r["original_task_id"] == "task-123"
    assert r["server_browser_used"] is False
