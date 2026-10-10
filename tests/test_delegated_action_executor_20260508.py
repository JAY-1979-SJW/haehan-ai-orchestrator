"""
사용자 위임 권한 실행기 테스트
"""
import pytest

from core.agent_runtime.runtime.permission.approval_audit_log import (
    clear_log,
    get_log_for_permission,
)
from core.agent_runtime.runtime.permission.delegated_action_executor import (
    EXEC_ALLOWED,
    EXEC_BLOCKED,
    EXEC_CONTENT_REJECTED,
    EXEC_NEED_PERMISSION,
    EXEC_USER_DIRECT,
    execute_delegated_action,
)
from core.agent_runtime.runtime.permission.delegated_permission_store import (
    clear_all,
    grant_permission,
    revoke,
)
from core.agent_runtime.runtime.safe_write_result_sanitizer import validate_write_result


@pytest.fixture(autouse=True)
def reset():
    clear_all()
    clear_log()
    yield
    clear_all()
    clear_log()


class TestExecutionWithPermission:
    def test_blog_publish_with_permission_allowed(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="블로그 테스트 게시글입니다."
        )
        assert result["status"] == EXEC_ALLOWED
        assert result["ok"] is True

    def test_cafe_post_write_with_permission_allowed(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        result = execute_delegated_action(
            "cafe_post_write", "cafe.naver.com", perm["permission_id"],
            content="카페 테스트 게시글."
        )
        assert result["status"] == EXEC_ALLOWED

    def test_cafe_comment_write_with_permission_allowed(self):
        perm = grant_permission("cafe_comment_write", "cafe.naver.com")
        result = execute_delegated_action(
            "cafe_comment_write", "cafe.naver.com", perm["permission_id"],
            content="테스트 댓글입니다."
        )
        assert result["status"] == EXEC_ALLOWED

    def test_result_has_no_sensitive_fields(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="테스트 게시글."
        )
        safe_result = result["result"]
        violations = validate_write_result(safe_result)
        assert violations == []

    def test_result_safe_fields_always_false(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="테스트."
        )
        r = result["result"]
        assert r["sensitive_data_collected"] is False
        assert r["cookie_exported"] is False
        assert r["session_exported"] is False
        assert r["password_collected"] is False
        assert r["otp_collected"] is False
        assert r["certificate_password_collected"] is False

    def test_one_time_permission_reuse_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", max_executions=1)
        execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="첫 번째 게시."
        )
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="두 번째 게시."
        )
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_revoked_permission_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="게시 시도."
        )
        assert result["status"] == EXEC_NEED_PERMISSION


class TestExecutionWithoutPermission:
    def test_blog_publish_without_permission_blocked(self):
        result = execute_delegated_action("blog_publish", "blog.naver.com", None,
                                          content="게시 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["ok"] is False

    def test_cafe_post_write_without_permission_blocked(self):
        result = execute_delegated_action("cafe_post_write", "cafe.naver.com", None,
                                          content="게시 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION


class TestBlockedActions:
    def test_password_save_blocked(self):
        result = execute_delegated_action("password_save", "example.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_cookie_export_blocked(self):
        result = execute_delegated_action("cookie_export", "example.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_auto_sign_blocked(self):
        result = execute_delegated_action("auto_sign", "example.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_auto_payment_blocked(self):
        result = execute_delegated_action("auto_payment", "example.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_npki_access_blocked(self):
        result = execute_delegated_action("npki_access", "example.com", None)
        assert result["status"] == EXEC_BLOCKED


class TestUserDirectRequired:
    def test_otp_input_user_direct(self):
        result = execute_delegated_action("otp_input", "example.com", None)
        assert result["status"] == EXEC_USER_DIRECT

    def test_bid_final_submit_user_direct(self):
        result = execute_delegated_action("bid_final_submit", "g2b.go.kr", None)
        assert result["status"] == EXEC_USER_DIRECT

    def test_e_sign_user_direct(self):
        result = execute_delegated_action("e_sign", "example.com", None)
        assert result["status"] == EXEC_USER_DIRECT


class TestAuditLog:
    def test_execution_creates_audit_log(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="감사 로그 테스트."
        )
        logs = get_log_for_permission(perm["permission_id"])
        assert len(logs) >= 2  # STARTED + COMPLETED

    def test_blocked_execution_creates_audit_log(self):
        from core.agent_runtime.runtime.permission.approval_audit_log import (
            EVENT_EXECUTION_BLOCKED,
            get_log,
        )
        execute_delegated_action("password_save", "example.com", None)
        log = get_log()
        blocked_entries = [e for e in log if e["event"] == EVENT_EXECUTION_BLOCKED]
        assert len(blocked_entries) >= 1

    def test_audit_log_has_no_sensitive_data(self):
        from core.agent_runtime.runtime.permission.approval_audit_log import get_log, has_sensitive_data
        perm = grant_permission("blog_publish", "blog.naver.com")
        execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="테스트 게시글."
        )
        for entry in get_log():
            assert has_sensitive_data(entry) is False


class TestContentGuardInExecutor:
    def test_content_mismatch_rejected(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"],
            content="실제 다른 내용입니다.",
            approved_preview="승인된 내용입니다.",
        )
        assert result["status"] == EXEC_CONTENT_REJECTED
