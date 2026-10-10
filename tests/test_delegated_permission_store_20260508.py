"""
사용자 위임 권한 저장소 테스트
"""
import pytest

from core.agent_runtime.runtime.permission.delegated_permission_policy import (
    CHECK_ALLOWED,
    CHECK_EXHAUSTED,
    CHECK_EXPIRED,
    CHECK_REVOKED,
    CHECK_SCOPE_EXCEEDED,
    PERM_ACTIVE,
    PERM_REVOKED,
)
from core.agent_runtime.runtime.permission.delegated_permission_store import (
    clear_all,
    get_permission,
    grant_permission,
    list_active_permissions,
    revoke,
    use_permission,
)


@pytest.fixture(autouse=True)
def reset_store():
    clear_all()
    yield
    clear_all()


class TestGrantPermission:
    def test_grant_returns_permission(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        assert perm["action"] == "blog_publish"
        assert perm["status"] == PERM_ACTIVE

    def test_granted_permission_retrievable(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        fetched = get_permission(perm["permission_id"])
        assert fetched is not None
        assert fetched["action"] == "cafe_post_write"

    def test_blocked_action_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("password_save", "example.com")

    def test_otp_save_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("otp_save", "example.com")

    def test_cookie_export_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("cookie_export", "example.com")

    def test_auto_sign_cannot_be_granted(self):
        with pytest.raises(ValueError):
            grant_permission("auto_sign", "example.com")


class TestRevokePermission:
    def test_revoke_success(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = revoke(perm["permission_id"])
        assert result is True

    def test_revoked_permission_status(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        fetched = get_permission(perm["permission_id"])
        assert fetched["status"] == PERM_REVOKED

    def test_revoke_nonexistent_returns_false(self):
        assert revoke("nonexistent-id") is False

    def test_revoked_permission_blocked_on_use(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = use_permission(perm["permission_id"], "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_REVOKED


class TestUsePermission:
    def test_first_use_allowed(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = use_permission(perm["permission_id"], "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_ALLOWED

    def test_one_time_permission_second_use_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", max_executions=1)
        use_permission(perm["permission_id"], "blog_publish", "blog.naver.com")
        result = use_permission(perm["permission_id"], "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_EXHAUSTED

    def test_multi_use_permission_counts(self):
        perm = grant_permission("cafe_comment_write", "cafe.naver.com", max_executions=3)
        for _ in range(3):
            r = use_permission(perm["permission_id"], "cafe_comment_write", "cafe.naver.com")
            assert r["result"] == CHECK_ALLOWED
        r = use_permission(perm["permission_id"], "cafe_comment_write", "cafe.naver.com")
        assert r["result"] == CHECK_EXHAUSTED

    def test_wrong_domain_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = use_permission(perm["permission_id"], "blog_publish", "other.com")
        assert result["result"] == CHECK_SCOPE_EXCEEDED

    def test_nonexistent_permission_required(self):
        from core.agent_runtime.runtime.permission.delegated_permission_policy import CHECK_PERMISSION_REQUIRED
        result = use_permission("no-such-id", "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_PERMISSION_REQUIRED

    def test_expired_permission_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", duration_seconds=0)
        import time; time.sleep(0.01)
        result = use_permission(perm["permission_id"], "blog_publish", "blog.naver.com")
        assert result["result"] == CHECK_EXPIRED


class TestListActivePermissions:
    def test_active_permissions_listed(self):
        grant_permission("blog_publish", "blog.naver.com")
        grant_permission("cafe_post_write", "cafe.naver.com")
        active = list_active_permissions()
        assert len(active) == 2

    def test_revoked_not_in_active_list(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        grant_permission("cafe_post_write", "cafe.naver.com")
        revoke(perm["permission_id"])
        active = list_active_permissions()
        assert len(active) == 1
        assert active[0]["action"] == "cafe_post_write"
