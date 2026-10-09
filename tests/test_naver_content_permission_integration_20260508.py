"""
네이버 콘텐츠 + 위임 권한 통합 테스트

권한 모델 연동 / 보안 정책 / 회귀 검증
"""

import pytest

from core.agent_runtime.runtime.permission.approval_audit_log import (
    EVENT_EXECUTION_COMPLETED,
    EVENT_EXECUTION_STARTED,
    clear_log,
    get_log,
    get_log_for_permission,
    has_sensitive_data,
)
from core.agent_runtime.runtime.permission.content_workflow_policy import (
    GRADE_USER_DIRECT,
    get_workflow_grade,
    is_workflow_auto_allowed,
    requires_permission,
)
from core.agent_runtime.runtime.permission.delegated_action_executor import (
    EXEC_ALLOWED,
    EXEC_BLOCKED,
    EXEC_NEED_PERMISSION,
    EXEC_USER_DIRECT,
    execute_delegated_action,
)
from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_EXHAUSTED,
    CHECK_EXPIRED,
    CHECK_REVOKED,
    CHECK_SCOPE_EXCEEDED,
)
from core.agent_runtime.runtime.permission.delegated_permission_store import (
    clear_all,
    grant_permission,
    revoke,
)


@pytest.fixture(autouse=True)
def reset():
    clear_all()
    clear_log()
    yield
    clear_all()
    clear_log()


class TestNaverWorkflowGrades:
    def test_cafe_탐색_auto_allowed(self):
        assert is_workflow_auto_allowed("cafe_search") is True

    def test_카페_게시글읽기_auto_allowed(self):
        assert is_workflow_auto_allowed("cafe_read_post") is True

    def test_블로그_초안_auto_allowed(self):
        assert is_workflow_auto_allowed("blog_generate_title") is True

    def test_블로그_본문_auto_allowed(self):
        assert is_workflow_auto_allowed("blog_generate_body") is True

    def test_블로그_임시저장_auto_allowed(self):
        assert is_workflow_auto_allowed("blog_save_draft") is True

    def test_블로그_발행_requires_permission(self):
        assert requires_permission("blog_publish") is True

    def test_카페_글쓰기_requires_permission(self):
        assert requires_permission("cafe_post_write") is True

    def test_카페_댓글_requires_permission(self):
        assert requires_permission("cafe_comment_write") is True

    def test_블로그_수정_requires_permission(self):
        assert requires_permission("blog_edit") is True

    def test_블로그_삭제_requires_permission(self):
        assert requires_permission("blog_delete") is True

    def test_예약_발행_requires_permission(self):
        assert requires_permission("blog_schedule_publish") is True

    def test_네이버_로그인_user_direct(self):
        assert get_workflow_grade("naver_login") == GRADE_USER_DIRECT

    def test_비밀번호_입력_user_direct(self):
        assert get_workflow_grade("login_password_input") == GRADE_USER_DIRECT

    def test_otp_user_direct(self):
        assert get_workflow_grade("otp_input") == GRADE_USER_DIRECT


class TestPermissionConstraintsNaver:
    def test_blog_publish_no_permission_blocked(self):
        result = execute_delegated_action("blog_publish", "blog.naver.com", None, content="발행 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_cafe_post_no_permission_blocked(self):
        result = execute_delegated_action("cafe_post_write", "cafe.naver.com", None, content="게시 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_cafe_comment_no_permission_blocked(self):
        result = execute_delegated_action("cafe_comment_write", "cafe.naver.com", None, content="댓글 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_blog_publish_with_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"], content="블로그 게시글."
        )
        assert result["status"] == EXEC_ALLOWED

    def test_cafe_post_with_permission(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        result = execute_delegated_action(
            "cafe_post_write", "cafe.naver.com", perm["permission_id"], content="카페 게시글."
        )
        assert result["status"] == EXEC_ALLOWED

    def test_cafe_comment_with_permission(self):
        perm = grant_permission("cafe_comment_write", "cafe.naver.com")
        result = execute_delegated_action(
            "cafe_comment_write", "cafe.naver.com", perm["permission_id"], content="카페 댓글."
        )
        assert result["status"] == EXEC_ALLOWED

    def test_expired_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com", duration_seconds=0)
        import time

        time.sleep(0.01)
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="발행 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_EXPIRED

    def test_revoked_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="발행 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_REVOKED

    def test_scope_exceeded(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "other.com", perm["permission_id"], content="발행 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_SCOPE_EXCEEDED

    def test_max_executions_exceeded(self):
        perm = grant_permission("cafe_comment_write", "cafe.naver.com", max_executions=2)
        for _ in range(2):
            execute_delegated_action("cafe_comment_write", "cafe.naver.com", perm["permission_id"], content="댓글.")
        result = execute_delegated_action(
            "cafe_comment_write", "cafe.naver.com", perm["permission_id"], content="3번째 댓글."
        )
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_EXHAUSTED


class TestAuditLogNaver:
    def test_blog_publish_creates_audit_log(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="감사 로그 테스트.")
        logs = get_log_for_permission(perm["permission_id"])
        events = {e["event"] for e in logs}
        assert EVENT_EXECUTION_STARTED in events
        assert EVENT_EXECUTION_COMPLETED in events

    def test_audit_log_no_sensitive_data(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        for entry in get_log():
            assert has_sensitive_data(entry) is False


class TestSafeResultNaver:
    def test_publish_result_no_password(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        r = result["result"]
        assert "password" not in r
        assert "otp" not in r
        assert "cookie" not in r
        assert "session" not in r
        assert "token" not in r

    def test_publish_result_safe_fields_false(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        r = result["result"]
        assert r["sensitive_data_collected"] is False
        assert r["cookie_exported"] is False
        assert r["password_collected"] is False
        assert r["otp_collected"] is False
        assert r["certificate_password_collected"] is False


class TestSpamAndSecurityBlocked:
    def test_bulk_spam_comment_blocked(self):
        result = execute_delegated_action("bulk_spam_comment", "cafe.naver.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_bulk_spam_post_blocked(self):
        result = execute_delegated_action("bulk_spam_post", "blog.naver.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_password_save_blocked(self):
        result = execute_delegated_action("password_save", "naver.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_cookie_export_blocked(self):
        result = execute_delegated_action("cookie_export", "naver.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_session_export_blocked(self):
        result = execute_delegated_action("session_export", "naver.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_otp_save_blocked(self):
        result = execute_delegated_action("otp_save", "nid.naver.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_otp_input_user_direct(self):
        result = execute_delegated_action("otp_input", "nid.naver.com", None)
        assert result["status"] == EXEC_USER_DIRECT

    def test_login_password_input_user_direct(self):
        result = execute_delegated_action("login_password_input", "nid.naver.com", None)
        assert result["status"] == EXEC_USER_DIRECT

    def test_ungrantable_password_save(self):
        with pytest.raises(ValueError):
            grant_permission("password_save", "naver.com")

    def test_ungrantable_otp_save(self):
        with pytest.raises(ValueError):
            grant_permission("otp_save", "nid.naver.com")

    def test_ungrantable_cookie_export(self):
        with pytest.raises(ValueError):
            grant_permission("cookie_export", "naver.com")


class TestExistingSystemRegression:
    def test_g2b_read_page_still_auto_allowed(self):
        result = execute_delegated_action("read_page", "www.g2b.go.kr", None)
        assert result["status"] == EXEC_ALLOWED

    def test_g2b_auto_bid_still_blocked(self):
        result = execute_delegated_action("auto_bid_submit", "www.g2b.go.kr", None)
        assert result["status"] == EXEC_BLOCKED

    def test_existing_security_guard(self):
        from ai_orchestrator.contracts.local_task_protocol import build_task
        from core.agent_runtime.runtime.security_guard import validate_task_before_run

        task = build_task("read_page", "https://www.g2b.go.kr/", domain="www.g2b.go.kr")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_existing_auth_wait_controller(self):
        from ai_orchestrator.contracts.local_task_protocol import (
            STATUS_WAITING_USER_AUTH,
        )
        from core.agent_runtime.runtime.auth.auth_wait_controller import (
            AUTH_SIGNAL_LOGIN,
            enter_auth_wait,
        )

        result = enter_auth_wait("regression-naver", AUTH_SIGNAL_LOGIN, "nid.naver.com")
        assert result["status"] == STATUS_WAITING_USER_AUTH
        assert result["sensitive_data_collected"] is False

    def test_naver_domain_profile_registered(self):
        from ai_orchestrator.browser_tool.policy.domain_profile_registry import (
            get_domain_profile,
        )

        profile = get_domain_profile("cafe.naver.com")
        assert profile["default_execution"] == "LOCAL_BROWSER_DEFAULT"

    def test_download_policy_still_works(self):
        from core.agent_runtime.runtime.download.download_policy import check_file

        assert check_file("입찰공고문.pdf", task_downloaded_files=["입찰공고문.pdf"])["upload_allowed"] is True
        assert check_file("cert.pfx", task_downloaded_files=["cert.pfx"])["upload_allowed"] is False
