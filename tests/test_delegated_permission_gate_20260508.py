"""
사용자 위임 권한 게이트 테스트
"""
import pytest

from core.agent_runtime.runtime.permission.delegated_permission_gate import (
    GATE_BLOCKED,
    GATE_NEED_PERMISSION,
    GATE_PASS,
    GATE_USER_DIRECT,
    evaluate_gate,
)
from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_ALLOWED,
    CHECK_BLOCKED,
    CHECK_EXHAUSTED,
    CHECK_PERMISSION_REQUIRED,
    CHECK_REVOKED,
    CHECK_SCOPE_EXCEEDED,
)
from core.agent_runtime.runtime.permission.delegated_permission_store import (
    clear_all,
    grant_permission,
    revoke,
)


@pytest.fixture(autouse=True)
def reset_store():
    clear_all()
    yield
    clear_all()


class TestGateAutoAllowed:
    def test_read_page_passes_without_permission(self):
        result = evaluate_gate("read_page", "example.com")
        assert result["gate"] == GATE_PASS

    def test_extract_text_passes(self):
        result = evaluate_gate("extract_text", "example.com")
        assert result["gate"] == GATE_PASS

    def test_search_passes(self):
        result = evaluate_gate("search", "example.com")
        assert result["gate"] == GATE_PASS

    def test_download_file_passes(self):
        result = evaluate_gate("download_file", "example.com")
        assert result["gate"] == GATE_PASS


class TestGateUserDelegated:
    def test_blog_publish_without_permission_needs_permission(self):
        result = evaluate_gate("blog_publish", "blog.naver.com")
        assert result["gate"] == GATE_NEED_PERMISSION
        assert result["check_result"] == CHECK_PERMISSION_REQUIRED

    def test_cafe_post_write_without_permission(self):
        result = evaluate_gate("cafe_post_write", "cafe.naver.com")
        assert result["gate"] == GATE_NEED_PERMISSION

    def test_cafe_comment_write_without_permission(self):
        result = evaluate_gate("cafe_comment_write", "cafe.naver.com")
        assert result["gate"] == GATE_NEED_PERMISSION

    def test_blog_publish_with_valid_permission_passes(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = evaluate_gate("blog_publish", "blog.naver.com", perm["permission_id"])
        assert result["gate"] == GATE_PASS
        assert result["check_result"] == CHECK_ALLOWED

    def test_cafe_post_write_with_valid_permission_passes(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        result = evaluate_gate("cafe_post_write", "cafe.naver.com", perm["permission_id"])
        assert result["gate"] == GATE_PASS

    def test_revoked_permission_needs_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = evaluate_gate("blog_publish", "blog.naver.com", perm["permission_id"])
        assert result["gate"] == GATE_NEED_PERMISSION
        assert result["check_result"] == CHECK_REVOKED

    def test_exhausted_permission_needs_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com", max_executions=1)
        # 첫 번째 사용 (게이트 통과 + 횟수 차감)
        evaluate_gate("blog_publish", "blog.naver.com", perm["permission_id"])
        # 두 번째 사용
        result = evaluate_gate("blog_publish", "blog.naver.com", perm["permission_id"])
        assert result["gate"] == GATE_NEED_PERMISSION
        assert result["check_result"] == CHECK_EXHAUSTED

    def test_scope_exceeded_wrong_domain(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = evaluate_gate("blog_publish", "other.com", perm["permission_id"])
        assert result["gate"] == GATE_NEED_PERMISSION
        assert result["check_result"] == CHECK_SCOPE_EXCEEDED

    def test_expired_permission_needs_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com", duration_seconds=0)
        import time; time.sleep(0.01)
        result = evaluate_gate("blog_publish", "blog.naver.com", perm["permission_id"])
        assert result["gate"] == GATE_NEED_PERMISSION


class TestGateBlocked:
    def test_password_save_blocked(self):
        result = evaluate_gate("password_save", "example.com")
        assert result["gate"] == GATE_BLOCKED
        assert result["check_result"] == CHECK_BLOCKED

    def test_otp_save_blocked(self):
        result = evaluate_gate("otp_save", "example.com")
        assert result["gate"] == GATE_BLOCKED

    def test_cookie_export_blocked(self):
        result = evaluate_gate("cookie_export", "example.com")
        assert result["gate"] == GATE_BLOCKED

    def test_session_export_blocked(self):
        result = evaluate_gate("session_export", "example.com")
        assert result["gate"] == GATE_BLOCKED

    def test_auto_sign_blocked(self):
        result = evaluate_gate("auto_sign", "example.com")
        assert result["gate"] == GATE_BLOCKED

    def test_auto_bid_submit_blocked(self):
        result = evaluate_gate("auto_bid_submit", "g2b.go.kr")
        assert result["gate"] == GATE_BLOCKED

    def test_auto_payment_blocked(self):
        result = evaluate_gate("auto_payment", "example.com")
        assert result["gate"] == GATE_BLOCKED

    def test_npki_access_blocked(self):
        result = evaluate_gate("npki_access", "example.com")
        assert result["gate"] == GATE_BLOCKED

    def test_cert_password_save_blocked(self):
        result = evaluate_gate("cert_password_save", "example.com")
        assert result["gate"] == GATE_BLOCKED


class TestGateUserDirect:
    def test_otp_input_user_direct(self):
        result = evaluate_gate("otp_input", "example.com")
        assert result["gate"] == GATE_USER_DIRECT

    def test_cert_password_input_user_direct(self):
        result = evaluate_gate("cert_password_input", "example.com")
        assert result["gate"] == GATE_USER_DIRECT

    def test_bid_final_submit_user_direct(self):
        result = evaluate_gate("bid_final_submit", "g2b.go.kr")
        assert result["gate"] == GATE_USER_DIRECT

    def test_e_sign_user_direct(self):
        result = evaluate_gate("e_sign", "example.com")
        assert result["gate"] == GATE_USER_DIRECT

    def test_confirm_payment_user_direct(self):
        result = evaluate_gate("confirm_payment", "example.com")
        assert result["gate"] == GATE_USER_DIRECT
