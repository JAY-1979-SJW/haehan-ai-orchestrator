"""
사용자 위임 권한 정책 테스트
"""

import pytest

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
    classify_action,
    is_auto_allowed,
    is_blocked,
    is_delegatable,
    is_user_direct_required,
)
from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_ALLOWED,
    CHECK_BLOCKED,
    CHECK_EXHAUSTED,
    CHECK_EXPIRED,
    CHECK_PERMISSION_REQUIRED,
    CHECK_REVOKED,
    CHECK_SCOPE_EXCEEDED,
    PERM_ACTIVE,
    build_permission,
    check_permission,
    increment_execution,
    revoke_permission,
)


class TestActionRiskGrade:
    def test_blog_publish_is_user_delegated(self):
        assert classify_action("blog_publish") == GRADE_USER_DELEGATED

    def test_cafe_post_write_is_user_delegated(self):
        assert classify_action("cafe_post_write") == GRADE_USER_DELEGATED

    def test_cafe_comment_write_is_user_delegated(self):
        assert classify_action("cafe_comment_write") == GRADE_USER_DELEGATED

    def test_blog_edit_is_user_delegated(self):
        assert classify_action("blog_edit") == GRADE_USER_DELEGATED

    def test_blog_delete_is_user_delegated(self):
        assert classify_action("blog_delete") == GRADE_USER_DELEGATED

    def test_blog_schedule_publish_is_user_delegated(self):
        assert classify_action("blog_schedule_publish") == GRADE_USER_DELEGATED

    def test_read_page_is_auto_allowed(self):
        assert classify_action("read_page") == GRADE_AUTO_ALLOWED

    def test_extract_text_is_auto_allowed(self):
        assert classify_action("extract_text") == GRADE_AUTO_ALLOWED

    def test_search_is_auto_allowed(self):
        assert classify_action("search") == GRADE_AUTO_ALLOWED

    def test_download_file_is_auto_allowed(self):
        assert classify_action("download_file") == GRADE_AUTO_ALLOWED

    def test_otp_input_is_user_direct(self):
        assert classify_action("otp_input") == GRADE_USER_DIRECT

    def test_cert_password_input_is_user_direct(self):
        assert classify_action("cert_password_input") == GRADE_USER_DIRECT

    def test_bid_final_submit_is_user_direct(self):
        assert classify_action("bid_final_submit") == GRADE_USER_DIRECT

    def test_confirm_payment_is_user_direct(self):
        assert classify_action("confirm_payment") == GRADE_USER_DIRECT

    def test_e_sign_is_user_direct(self):
        assert classify_action("e_sign") == GRADE_USER_DIRECT

    def test_password_save_is_blocked(self):
        assert classify_action("password_save") == GRADE_BLOCKED

    def test_otp_save_is_blocked(self):
        assert classify_action("otp_save") == GRADE_BLOCKED

    def test_cert_password_save_is_blocked(self):
        assert classify_action("cert_password_save") == GRADE_BLOCKED

    def test_cookie_export_is_blocked(self):
        assert classify_action("cookie_export") == GRADE_BLOCKED

    def test_session_export_is_blocked(self):
        assert classify_action("session_export") == GRADE_BLOCKED

    def test_npki_access_is_blocked(self):
        assert classify_action("npki_access") == GRADE_BLOCKED

    def test_auto_sign_is_blocked(self):
        assert classify_action("auto_sign") == GRADE_BLOCKED

    def test_auto_bid_submit_is_blocked(self):
        assert classify_action("auto_bid_submit") == GRADE_BLOCKED

    def test_auto_payment_is_blocked(self):
        assert classify_action("auto_payment") == GRADE_BLOCKED

    def test_auto_transfer_is_blocked(self):
        assert classify_action("auto_transfer") == GRADE_BLOCKED

    def test_bulk_spam_post_is_blocked(self):
        assert classify_action("bulk_spam_post") == GRADE_BLOCKED

    def test_bulk_spam_comment_is_blocked(self):
        assert classify_action("bulk_spam_comment") == GRADE_BLOCKED

    def test_is_delegatable_blog_publish(self):
        assert is_delegatable("blog_publish") is True

    def test_is_blocked_password_save(self):
        assert is_blocked("password_save") is True

    def test_is_auto_allowed_read_page(self):
        assert is_auto_allowed("read_page") is True

    def test_is_user_direct_otp_input(self):
        assert is_user_direct_required("otp_input") is True


class TestBuildPermission:
    def test_blog_publish_permission_created(self):
        perm = build_permission("blog_publish", "blog.naver.com")
        assert perm["action"] == "blog_publish"
        assert perm["status"] == PERM_ACTIVE
        assert perm["execution_count"] == 0

    def test_permission_has_required_fields(self):
        perm = build_permission("cafe_post_write", "cafe.naver.com", account="user1")
        assert "permission_id" in perm
        assert "granted_at" in perm
        assert "expires_at" in perm
        assert perm["max_executions"] == 1

    def test_blocked_action_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("password_save", "example.com")

    def test_cookie_export_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("cookie_export", "example.com")

    def test_session_export_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("session_export", "example.com")

    def test_npki_access_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("npki_access", "example.com")

    def test_auto_sign_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("auto_sign", "example.com")

    def test_auto_bid_submit_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("auto_bid_submit", "example.com")

    def test_auto_payment_raises(self):
        with pytest.raises(ValueError, match="권한 부여 불가"):
            build_permission("auto_payment", "example.com")

    def test_auto_direct_action_raises(self):
        # USER_DIRECT 등급도 위임 불가
        with pytest.raises(ValueError, match="위임 불가"):
            build_permission("otp_input", "example.com")

    def test_max_executions_spam_limit(self):
        with pytest.raises(ValueError, match="최대 허용"):
            build_permission("blog_publish", "blog.naver.com", max_executions=100)

    def test_max_executions_50_ok(self):
        perm = build_permission("cafe_comment_write", "cafe.naver.com", max_executions=50)
        assert perm["max_executions"] == 50


class TestCheckPermission:
    def test_valid_permission_allowed(self):
        perm = build_permission("blog_publish", "blog.naver.com")
        result = check_permission(perm, "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_ALLOWED

    def test_none_permission_required(self):
        result = check_permission(None, "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_PERMISSION_REQUIRED

    def test_revoked_permission_blocked(self):
        perm = build_permission("blog_publish", "blog.naver.com")
        revoke_permission(perm)
        result = check_permission(perm, "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_REVOKED

    def test_exhausted_permission_blocked(self):
        perm = build_permission("blog_publish", "blog.naver.com", max_executions=1)
        increment_execution(perm)
        result = check_permission(perm, "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_EXHAUSTED

    def test_expired_permission_blocked(self):
        perm = build_permission("blog_publish", "blog.naver.com", duration_seconds=0)
        # duration_seconds=0 → 즉시 만료
        import time

        time.sleep(0.01)
        result = check_permission(perm, "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_EXPIRED

    def test_wrong_action_scope_exceeded(self):
        perm = build_permission("blog_publish", "blog.naver.com")
        result = check_permission(perm, "cafe_post_write", "blog.naver.com")
        assert result["result"] == CHECK_SCOPE_EXCEEDED

    def test_wrong_domain_scope_exceeded(self):
        perm = build_permission("blog_publish", "blog.naver.com")
        result = check_permission(perm, "blog_publish", "other.com")
        assert result["result"] == CHECK_SCOPE_EXCEEDED

    def test_wrong_account_scope_exceeded(self):
        perm = build_permission("blog_publish", "blog.naver.com", account="userA")
        result = check_permission(perm, "blog_publish", "blog.naver.com", account="userB")
        assert result["result"] == CHECK_SCOPE_EXCEEDED

    def test_one_time_permission_reuse_blocked(self):
        perm = build_permission("blog_publish", "blog.naver.com", max_executions=1)
        increment_execution(perm)
        result = check_permission(perm, "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_EXHAUSTED

    def test_blocked_action_check(self):
        perm = build_permission("blog_publish", "blog.naver.com")
        result = check_permission(perm, "password_save", "example.com")
        assert result["result"] == CHECK_BLOCKED
