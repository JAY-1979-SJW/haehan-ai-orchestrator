"""
권한 실행 audit log 테스트
"""
import pytest

from core.agent_runtime.runtime.permission.approval_audit_log import (
    EVENT_EXECUTION_BLOCKED,
    EVENT_EXECUTION_COMPLETED,
    EVENT_EXECUTION_STARTED,
    EVENT_PERMISSION_GRANTED,
    EVENT_PERMISSION_REVOKED,
    clear_log,
    get_log,
    get_log_for_permission,
    has_sensitive_data,
    log_execution_blocked,
    log_execution_completed,
    log_execution_started,
    log_permission_granted,
    log_permission_revoked,
)


@pytest.fixture(autouse=True)
def reset():
    clear_log()
    yield
    clear_log()


class TestLogEvents:
    def test_permission_granted_logged(self):
        log_permission_granted("perm-001", "blog_publish", "blog.naver.com")
        log = get_log()
        assert any(e["event"] == EVENT_PERMISSION_GRANTED for e in log)

    def test_permission_revoked_logged(self):
        log_permission_revoked("perm-001", "blog_publish", "blog.naver.com")
        log = get_log()
        assert any(e["event"] == EVENT_PERMISSION_REVOKED for e in log)

    def test_execution_started_logged(self):
        log_execution_started("perm-001", "blog_publish", "blog.naver.com", "task-001")
        log = get_log()
        assert any(e["event"] == EVENT_EXECUTION_STARTED for e in log)

    def test_execution_completed_logged(self):
        log_execution_completed("perm-001", "blog_publish", "blog.naver.com", "task-001", ok=True)
        log = get_log()
        assert any(e["event"] == EVENT_EXECUTION_COMPLETED for e in log)

    def test_execution_blocked_logged(self):
        log_execution_blocked("password_save", "example.com", "BLOCKED 등급")
        log = get_log()
        assert any(e["event"] == EVENT_EXECUTION_BLOCKED for e in log)

    def test_entry_has_timestamp(self):
        e = log_permission_granted("perm-001", "blog_publish", "blog.naver.com")
        assert "timestamp" in e
        assert "log_id" in e

    def test_get_log_for_permission(self):
        log_execution_started("perm-A", "blog_publish", "blog.naver.com")
        log_execution_started("perm-B", "cafe_post_write", "cafe.naver.com")
        entries = get_log_for_permission("perm-A")
        assert all(e["permission_id"] == "perm-A" for e in entries)
        assert len(entries) == 1

    def test_content_preview_truncated(self):
        long_preview = "A" * 500
        e = log_execution_started("perm-001", "blog_publish", "blog.naver.com",
                                   content_preview=long_preview)
        assert len(e["content_preview"]) <= 200

    def test_log_limit(self):
        for i in range(10):
            log_execution_started(f"perm-{i}", "blog_publish", "blog.naver.com")
        log = get_log(limit=5)
        assert len(log) == 5


class TestNoSensitiveData:
    def test_has_sensitive_data_false_for_clean_entry(self):
        e = {"event": "EXECUTION_COMPLETED", "action": "blog_publish", "ok": True}
        assert has_sensitive_data(e) is False

    def test_has_sensitive_data_true_for_password(self):
        e = {"event": "EXECUTION_STARTED", "password": "secret"}
        assert has_sensitive_data(e) is True

    def test_has_sensitive_data_true_for_cookie(self):
        e = {"event": "EXECUTION_STARTED", "cookie": "abc123"}
        assert has_sensitive_data(e) is True

    def test_has_sensitive_data_true_for_otp(self):
        e = {"event": "EXECUTION_STARTED", "otp": "123456"}
        assert has_sensitive_data(e) is True

    def test_has_sensitive_data_true_for_token(self):
        e = {"event": "EXECUTION_STARTED", "token": "tok_abc"}
        assert has_sensitive_data(e) is True

    def test_log_entries_never_contain_sensitive_data(self):
        log_permission_granted("perm-001", "blog_publish", "blog.naver.com",
                               account="user1", max_executions=1)
        log_execution_started("perm-001", "blog_publish", "blog.naver.com",
                               task_id="t-001", content_preview="게시글 미리보기")
        log_execution_completed("perm-001", "blog_publish", "blog.naver.com",
                                 task_id="t-001", ok=True)
        for entry in get_log():
            assert has_sensitive_data(entry) is False
