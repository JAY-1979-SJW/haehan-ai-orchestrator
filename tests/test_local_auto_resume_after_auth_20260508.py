"""
auto_resume_after_auth 테스트
"""

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_COMPLETED,
    STATUS_USER_ACTION_REQUIRED,
)
from core.agent_runtime.runtime.auth.auto_resume_after_auth import (
    can_auto_resume,
    classify_resume_eligibility,
    resume_after_auth,
)


def _make_task(action: str) -> dict:
    return {
        "task_id": "resume-task-001",
        "task_type": "browser_task",
        "execution_mode": "LOCAL_PLAYWRIGHT",
        "action": action,
        "target_url": "https://example.com",
        "domain": "example.com",
        "readonly": True,
        "requires_user_presence": False,
        "timeout_seconds": 300,
        "metadata": {},
    }


def _mock_runner(task):
    return {
        "task_id": task["task_id"],
        "ok": True,
        "status": STATUS_COMPLETED,
        "current_url_host": "example.com",
        "title_hint": "업무 화면",
        "extracted_data": {"body_text_sample": "업무 내용"},
        "downloaded_files": [],
        "message_ko": "완료",
    }


class TestCanAutoResume:
    def test_read_page_allowed(self):
        assert can_auto_resume("read_page") is True

    def test_search_allowed(self):
        assert can_auto_resume("search") is True

    def test_download_file_allowed(self):
        assert can_auto_resume("download_file") is True

    def test_capture_screenshot_allowed(self):
        assert can_auto_resume("capture_screenshot") is True

    def test_extract_text_allowed(self):
        assert can_auto_resume("extract_text") is True

    def test_extract_table_allowed(self):
        assert can_auto_resume("extract_table") is True

    def test_detect_login_status_allowed(self):
        assert can_auto_resume("detect_login_status") is True

    def test_final_submit_forbidden(self):
        assert can_auto_resume("final_submit") is False

    def test_bid_submit_forbidden(self):
        assert can_auto_resume("bid_submit") is False

    def test_sign_forbidden(self):
        assert can_auto_resume("sign") is False

    def test_payment_forbidden(self):
        assert can_auto_resume("payment") is False

    def test_submit_forbidden(self):
        assert can_auto_resume("submit") is False

    def test_transfer_forbidden(self):
        assert can_auto_resume("transfer") is False

    def test_contract_submit_forbidden(self):
        assert can_auto_resume("contract_submit") is False


class TestResumeAfterAuth:
    def test_read_page_resumes_ok(self):
        task = _make_task("read_page")
        result = resume_after_auth(task, _mock_runner)
        assert result["ok"] is True
        assert result["sensitive_data_collected"] is False

    def test_download_file_resumes_ok(self):
        task = _make_task("download_file")
        result = resume_after_auth(task, _mock_runner)
        assert result["ok"] is True

    def test_extract_text_resumes_ok(self):
        task = _make_task("extract_text")
        result = resume_after_auth(task, _mock_runner)
        assert result["ok"] is True

    def test_final_submit_not_resumed(self):
        task = _make_task("final_submit")
        result = resume_after_auth(task, _mock_runner)
        assert result["status"] == STATUS_USER_ACTION_REQUIRED

    def test_bid_submit_not_resumed(self):
        task = _make_task("bid_submit")
        result = resume_after_auth(task, _mock_runner)
        assert result["status"] == STATUS_USER_ACTION_REQUIRED

    def test_sign_not_resumed(self):
        task = _make_task("sign")
        result = resume_after_auth(task, _mock_runner)
        assert result["status"] == STATUS_USER_ACTION_REQUIRED

    def test_payment_not_resumed(self):
        task = _make_task("payment")
        result = resume_after_auth(task, _mock_runner)
        assert result["status"] == STATUS_USER_ACTION_REQUIRED

    def test_result_sanitized(self):
        def runner_with_sensitive(task):
            r = _mock_runner(task)
            r["cookie"] = "secret"
            return r

        task = _make_task("read_page")
        result = resume_after_auth(task, runner_with_sensitive)
        assert "cookie" not in result or result.get("cookie") in (None, False, "")
        assert result.get("sensitive_data_collected") is False


class TestClassifyResumeEligibility:
    def test_read_page_eligible(self):
        r = classify_resume_eligibility("read_page")
        assert r["eligible"] is True

    def test_final_submit_not_eligible(self):
        r = classify_resume_eligibility("final_submit")
        assert r["eligible"] is False
        assert "사용자 직접" in r["reason"]

    def test_unknown_action_not_eligible(self):
        r = classify_resume_eligibility("unknown_action")
        assert r["eligible"] is False
