"""
사용자 위임 권한 실행 모델 통합 테스트

전체 흐름 검증:
- 블로그/카페/댓글 발행은 USER_DELEGATED_PERMISSION_REQUIRED
- 권한 부여 → 실행 → audit log → safe result
- 만료/철회/scope/횟수 초과 차단
- BLOCKED 등급 절대 차단
- 기존 auth wait / g2b read-only 회귀
"""

import pytest

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
    classify_action,
)
from core.agent_runtime.runtime.permission.approval_audit_log import (
    EVENT_EXECUTION_BLOCKED,
    EVENT_EXECUTION_COMPLETED,
    EVENT_EXECUTION_STARTED,
    clear_log,
    get_log,
    get_log_for_permission,
    has_sensitive_data,
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
from core.agent_runtime.runtime.safe_write_result_sanitizer import validate_write_result


@pytest.fixture(autouse=True)
def reset():
    clear_all()
    clear_log()
    yield
    clear_all()
    clear_log()


# ── 실행 등급 분류 ─────────────────────────────────────────────────────────────


class TestExecutionGradeClassification:
    def test_blog_publish_requires_user_delegated(self):
        assert classify_action("blog_publish") == GRADE_USER_DELEGATED

    def test_cafe_post_write_requires_user_delegated(self):
        assert classify_action("cafe_post_write") == GRADE_USER_DELEGATED

    def test_cafe_comment_write_requires_user_delegated(self):
        assert classify_action("cafe_comment_write") == GRADE_USER_DELEGATED

    def test_blog_edit_requires_user_delegated(self):
        assert classify_action("blog_edit") == GRADE_USER_DELEGATED

    def test_blog_delete_requires_user_delegated(self):
        assert classify_action("blog_delete") == GRADE_USER_DELEGATED

    def test_blog_schedule_publish_requires_user_delegated(self):
        assert classify_action("blog_schedule_publish") == GRADE_USER_DELEGATED

    def test_cafe_post_delete_requires_user_delegated(self):
        assert classify_action("cafe_post_delete") == GRADE_USER_DELEGATED

    def test_read_page_auto_allowed(self):
        assert classify_action("read_page") == GRADE_AUTO_ALLOWED

    def test_search_auto_allowed(self):
        assert classify_action("search") == GRADE_AUTO_ALLOWED

    def test_extract_text_auto_allowed(self):
        assert classify_action("extract_text") == GRADE_AUTO_ALLOWED

    def test_otp_input_user_direct(self):
        assert classify_action("otp_input") == GRADE_USER_DIRECT

    def test_password_save_blocked(self):
        assert classify_action("password_save") == GRADE_BLOCKED

    def test_cookie_export_blocked(self):
        assert classify_action("cookie_export") == GRADE_BLOCKED

    def test_auto_sign_blocked(self):
        assert classify_action("auto_sign") == GRADE_BLOCKED

    def test_auto_bid_submit_blocked(self):
        assert classify_action("auto_bid_submit") == GRADE_BLOCKED

    def test_auto_payment_blocked(self):
        assert classify_action("auto_payment") == GRADE_BLOCKED


# ── 권한 없이 차단 ─────────────────────────────────────────────────────────────


class TestNoPermissionBlocked:
    def test_blog_publish_without_permission(self):
        result = execute_delegated_action("blog_publish", "blog.naver.com", None, content="게시글.")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_cafe_post_write_without_permission(self):
        result = execute_delegated_action("cafe_post_write", "cafe.naver.com", None, content="게시글.")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_cafe_comment_write_without_permission(self):
        result = execute_delegated_action("cafe_comment_write", "cafe.naver.com", None, content="댓글.")
        assert result["status"] == EXEC_NEED_PERMISSION


# ── 권한 있으면 실행 ───────────────────────────────────────────────────────────


class TestWithPermissionAllowed:
    def test_blog_publish_with_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"], content="블로그 게시글 내용."
        )
        assert result["status"] == EXEC_ALLOWED
        assert result["ok"] is True

    def test_cafe_comment_with_permission(self):
        perm = grant_permission("cafe_comment_write", "cafe.naver.com")
        result = execute_delegated_action(
            "cafe_comment_write", "cafe.naver.com", perm["permission_id"], content="카페 댓글입니다."
        )
        assert result["status"] == EXEC_ALLOWED


# ── 만료/철회/scope/횟수 ──────────────────────────────────────────────────────


class TestPermissionConstraints:
    def test_expired_permission_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", duration_seconds=0)
        import time

        time.sleep(0.01)
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="게시 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        gate = result["gate"]
        assert gate["check_result"] == CHECK_EXPIRED

    def test_revoked_permission_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="게시 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_REVOKED

    def test_max_executions_exceeded_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", max_executions=2)
        for _ in range(2):
            execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="게시글.")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"], content="3번째 시도."
        )
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_EXHAUSTED

    def test_one_time_permission_reuse_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", max_executions=1)
        execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="1회 사용.")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"], content="재사용 시도."
        )
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_scope_exceeded_wrong_domain(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "other.com", perm["permission_id"], content="게시 시도.")
        assert result["status"] == EXEC_NEED_PERMISSION
        assert result["gate"]["check_result"] == CHECK_SCOPE_EXCEEDED


# ── 권한 부여 불가 (BLOCKED) ──────────────────────────────────────────────────


class TestUngrantableActions:
    def test_password_save_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("password_save", "example.com")

    def test_otp_save_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("otp_save", "example.com")

    def test_cert_password_save_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("cert_password_save", "example.com")

    def test_cookie_export_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("cookie_export", "example.com")

    def test_session_export_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("session_export", "example.com")

    def test_npki_access_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("npki_access", "example.com")

    def test_auto_sign_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("auto_sign", "example.com")

    def test_auto_bid_submit_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("auto_bid_submit", "example.com")

    def test_auto_payment_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("auto_payment", "example.com")

    def test_auto_transfer_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("auto_transfer", "example.com")

    def test_electronic_sign_cannot_be_granted(self):
        # USER_DIRECT 등급도 위임 불가
        with pytest.raises(ValueError):
            grant_permission("e_sign", "example.com")

    def test_bid_final_submit_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("bid_final_submit", "g2b.go.kr")

    def test_confirm_payment_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("confirm_payment", "example.com")


# ── safe result ───────────────────────────────────────────────────────────────


class TestSafeResult:
    def test_safe_result_no_sensitive_fields(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action(
            "blog_publish", "blog.naver.com", perm["permission_id"], content="테스트 게시글."
        )
        assert validate_write_result(result["result"]) == []

    def test_safe_result_no_password(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        assert "password" not in result["result"]

    def test_safe_result_no_cookie(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        assert "cookie" not in result["result"]

    def test_safe_result_no_otp(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        assert "otp" not in result["result"]

    def test_safe_result_no_session(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        assert "session" not in result["result"]

    def test_safe_result_fixed_false_fields(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트.")
        r = result["result"]
        assert r["sensitive_data_collected"] is False
        assert r["cookie_exported"] is False
        assert r["password_collected"] is False
        assert r["otp_collected"] is False
        assert r["certificate_password_collected"] is False


# ── audit log ─────────────────────────────────────────────────────────────────


class TestAuditLogIntegration:
    def test_execution_generates_audit_log(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="테스트 게시글.")
        logs = get_log_for_permission(perm["permission_id"])
        events = {e["event"] for e in logs}
        assert EVENT_EXECUTION_STARTED in events
        assert EVENT_EXECUTION_COMPLETED in events

    def test_blocked_execution_generates_audit_log(self):
        execute_delegated_action("password_save", "example.com", None)
        log = get_log()
        assert any(e["event"] == EVENT_EXECUTION_BLOCKED for e in log)

    def test_audit_log_no_sensitive_data(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        execute_delegated_action("blog_publish", "blog.naver.com", perm["permission_id"], content="감사 로그 테스트.")
        for entry in get_log():
            assert has_sensitive_data(entry) is False


# ── 스팸 차단 ─────────────────────────────────────────────────────────────────


class TestSpamBlocking:
    def test_bulk_spam_comment_action_blocked(self):
        result = execute_delegated_action("bulk_spam_comment", "example.com", None)
        assert result["status"] == EXEC_BLOCKED

    def test_bulk_spam_post_action_blocked(self):
        result = execute_delegated_action("bulk_spam_post", "example.com", None)
        assert result["status"] == EXEC_BLOCKED


# ── 기존 시스템 회귀 ──────────────────────────────────────────────────────────


class TestRegressionExistingSystem:
    def test_g2b_read_page_auto_allowed(self):
        """나라장터 read-only 작업은 위임 권한 없이 실행 가능."""
        result = execute_delegated_action("read_page", "www.g2b.go.kr", None)
        assert result["status"] == EXEC_ALLOWED

    def test_g2b_extract_text_auto_allowed(self):
        result = execute_delegated_action("extract_text", "www.g2b.go.kr", None)
        assert result["status"] == EXEC_ALLOWED

    def test_g2b_auto_bid_submit_blocked(self):
        """나라장터 자동 투찰은 권한 부여 대상 아님."""
        result = execute_delegated_action("auto_bid_submit", "www.g2b.go.kr", None)
        assert result["status"] == EXEC_BLOCKED

    def test_g2b_otp_input_user_direct(self):
        """OTP 입력은 사용자 직접 수행."""
        result = execute_delegated_action("otp_input", "www.g2b.go.kr", None)
        assert result["status"] == EXEC_USER_DIRECT

    def test_existing_security_guard_still_works(self):
        """기존 security_guard 모듈 회귀."""
        from ai_orchestrator.contracts.local_task_protocol import build_task
        from core.agent_runtime.runtime.security_guard import validate_task_before_run

        task = build_task("read_page", "https://www.g2b.go.kr/", domain="www.g2b.go.kr")
        guard = validate_task_before_run(task)
        assert guard["allowed"] is True

    def test_existing_auth_wait_controller_still_works(self):
        """기존 auth wait controller 회귀."""
        from ai_orchestrator.contracts.local_task_protocol import (
            STATUS_WAITING_USER_AUTH,
        )
        from core.agent_runtime.runtime.auth.auth_wait_controller import (
            AUTH_SIGNAL_LOGIN,
            enter_auth_wait,
        )

        result = enter_auth_wait("regression-task", AUTH_SIGNAL_LOGIN, "www.g2b.go.kr")
        assert result["status"] == STATUS_WAITING_USER_AUTH
        assert result["sensitive_data_collected"] is False

    def test_existing_auto_resume_after_auth_still_works(self):
        """기존 auto resume 회귀."""
        from core.agent_runtime.runtime.auth.auto_resume_after_auth import can_auto_resume

        assert can_auto_resume("read_page") is True
        assert can_auto_resume("submit") is False

    def test_existing_download_policy_still_works(self):
        """기존 다운로드 정책 회귀."""
        from core.agent_runtime.runtime.download.download_policy import check_file

        result = check_file("입찰공고문.pdf", task_downloaded_files=["입찰공고문.pdf"])
        assert result["upload_allowed"] is True
        result_cert = check_file("cert.pfx", task_downloaded_files=["cert.pfx"])
        assert result_cert["upload_allowed"] is False
