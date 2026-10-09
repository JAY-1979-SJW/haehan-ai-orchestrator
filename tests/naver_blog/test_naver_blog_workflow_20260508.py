"""
네이버 블로그 workflow 테스트
"""

import pytest

from core.agent_runtime.runtime.permission.content_workflow_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_USER_DELEGATED,
    requires_permission,
)
from core.agent_runtime.runtime.permission.delegated_action_executor import (
    EXEC_ALLOWED,
    EXEC_NEED_PERMISSION,
)
from core.agent_runtime.runtime.permission.delegated_permission_store import (
    clear_all,
    grant_permission,
    revoke,
)
from scripts.naver.blog.naver_blog_workflow import (
    STEP_DELETE,
    STEP_EDIT,
    STEP_GENERATE_BODY,
    STEP_GENERATE_TAGS,
    STEP_GENERATE_TITLE,
    STEP_PREVIEW,
    STEP_PUBLISH,
    STEP_SAVE_DRAFT,
    STEP_SCHEDULE_PUBLISH,
    delete_blog_post,
    edit_blog_post,
    generate_blog_draft,
    get_blog_workflow_grade,
    publish_blog_post,
    read_blog_post,
    schedule_blog_publish,
)
from scripts.naver.blog.naver_content_safe_result import validate_naver_result


@pytest.fixture(autouse=True)
def reset():
    clear_all()
    yield
    clear_all()


class TestBlogDraftGrade:
    def test_generate_title_auto_allowed(self):
        assert get_blog_workflow_grade(STEP_GENERATE_TITLE) == GRADE_AUTO_ALLOWED

    def test_generate_body_auto_allowed(self):
        assert get_blog_workflow_grade(STEP_GENERATE_BODY) == GRADE_AUTO_ALLOWED

    def test_generate_tags_auto_allowed(self):
        assert get_blog_workflow_grade(STEP_GENERATE_TAGS) == GRADE_AUTO_ALLOWED

    def test_preview_auto_allowed(self):
        assert get_blog_workflow_grade(STEP_PREVIEW) == GRADE_AUTO_ALLOWED

    def test_save_draft_auto_allowed(self):
        assert get_blog_workflow_grade(STEP_SAVE_DRAFT) == GRADE_AUTO_ALLOWED


class TestBlogPublishGrade:
    def test_publish_requires_permission(self):
        assert get_blog_workflow_grade(STEP_PUBLISH) == GRADE_USER_DELEGATED

    def test_schedule_publish_requires_permission(self):
        assert get_blog_workflow_grade(STEP_SCHEDULE_PUBLISH) == GRADE_USER_DELEGATED

    def test_edit_requires_permission(self):
        assert get_blog_workflow_grade(STEP_EDIT) == GRADE_USER_DELEGATED

    def test_delete_requires_permission(self):
        assert get_blog_workflow_grade(STEP_DELETE) == GRADE_USER_DELEGATED

    def test_set_visibility_requires_permission(self):
        assert requires_permission("blog_set_visibility") is True


class TestBlogDraftGeneration:
    def test_generate_draft_ok(self):
        draft = generate_blog_draft("파이썬 기초")
        assert draft["ok"] is True
        assert len(draft["title_candidates"]) >= 1
        assert draft["body_draft"] != ""

    def test_generate_draft_with_source(self):
        draft = generate_blog_draft(
            "네이버 카페 탐색",
            source_material=["카페 게시글 참고", "요약 자료"],
            keywords=["카페", "네이버", "커뮤니티"],
        )
        assert draft["ok"] is True
        assert len(draft["tag_candidates"]) >= 1

    def test_draft_safe_result(self):
        draft = generate_blog_draft("테스트 주제")
        violations = validate_naver_result(draft)
        assert violations == []

    def test_draft_no_password(self):
        draft = generate_blog_draft("테스트")
        assert "password" not in draft
        assert "cookie" not in draft
        assert "session" not in draft


class TestBlogPublishPermission:
    def test_publish_without_permission_blocked(self):
        result = publish_blog_post("블로그 내용입니다.", permission_id="")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_schedule_without_permission_blocked(self):
        result = schedule_blog_publish("블로그 내용.", permission_id="")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_edit_without_permission_blocked(self):
        result = edit_blog_post("수정 내용.", permission_id="")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_delete_without_permission_blocked(self):
        result = delete_blog_post(permission_id="")
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_publish_with_permission_allowed(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = publish_blog_post(
            "블로그 게시글 내용입니다.",
            permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_ALLOWED

    def test_schedule_with_permission_allowed(self):
        perm = grant_permission("blog_schedule_publish", "blog.naver.com")
        result = schedule_blog_publish(
            "예약 발행 블로그 내용.",
            permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_ALLOWED

    def test_edit_with_permission_allowed(self):
        perm = grant_permission("blog_edit", "blog.naver.com")
        result = edit_blog_post(
            "수정된 블로그 내용.",
            permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_ALLOWED

    def test_delete_with_permission_allowed(self):
        perm = grant_permission("blog_delete", "blog.naver.com")
        result = delete_blog_post(permission_id=perm["permission_id"])
        assert result["status"] == EXEC_ALLOWED

    def test_publish_result_safe(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = publish_blog_post("테스트 게시글.", permission_id=perm["permission_id"])
        violations = validate_naver_result(result.get("result", {}))
        assert violations == []

    def test_revoked_permission_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = publish_blog_post("게시 시도.", permission_id=perm["permission_id"])
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_expired_permission_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", duration_seconds=0)
        import time

        time.sleep(0.01)
        result = publish_blog_post("게시 시도.", permission_id=perm["permission_id"])
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_scope_exceeded_wrong_domain(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = publish_blog_post(
            "게시 시도.",
            permission_id=perm["permission_id"],
            domain="other.com",
        )
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_one_time_permission_reuse_blocked(self):
        perm = grant_permission("blog_publish", "blog.naver.com", max_executions=1)
        publish_blog_post("1회 발행.", permission_id=perm["permission_id"])
        result = publish_blog_post("2회 시도.", permission_id=perm["permission_id"])
        assert result["status"] == EXEC_NEED_PERMISSION


class TestBlogReadAutoAllowed:
    def test_read_blog_post_dryrun(self):
        result = read_blog_post("https://blog.naver.com/test/123")
        assert result["ok"] is True
        assert result["server_browser_used"] is False
