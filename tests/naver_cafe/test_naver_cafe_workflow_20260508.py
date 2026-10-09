"""
네이버 카페 workflow 테스트
"""
import pytest

from core.agent_runtime.runtime.permission.content_workflow_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_USER_DELEGATED,
    is_workflow_auto_allowed,
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
from scripts.naver.blog.naver_content_safe_result import validate_naver_result
from scripts.naver.cafe.naver_cafe_workflow import (
    STEP_COMMENT_WRITE,
    STEP_POST_WRITE,
    STEP_READ_POST,
    STEP_SEARCH,
    generate_blog_material_from_post,
    get_cafe_workflow_grade,
    read_cafe_post,
    search_cafe,
    write_cafe_comment,
    write_cafe_post,
)


@pytest.fixture(autouse=True)
def reset():
    clear_all()
    yield
    clear_all()


class TestCafeReadGrade:
    def test_cafe_search_auto_allowed(self):
        assert get_cafe_workflow_grade(STEP_SEARCH) == GRADE_AUTO_ALLOWED

    def test_cafe_read_post_auto_allowed(self):
        assert get_cafe_workflow_grade(STEP_READ_POST) == GRADE_AUTO_ALLOWED

    def test_cafe_extract_summary_auto_allowed(self):
        assert is_workflow_auto_allowed("cafe_extract_summary") is True

    def test_cafe_extract_keywords_auto_allowed(self):
        assert is_workflow_auto_allowed("cafe_extract_keywords") is True

    def test_cafe_generate_draft_auto_allowed(self):
        assert is_workflow_auto_allowed("cafe_generate_draft") is True

    def test_cafe_generate_comment_candidate_auto_allowed(self):
        assert is_workflow_auto_allowed("cafe_generate_comment_candidate") is True


class TestCafeWriteGrade:
    def test_cafe_post_write_requires_permission(self):
        assert get_cafe_workflow_grade(STEP_POST_WRITE) == GRADE_USER_DELEGATED

    def test_cafe_comment_write_requires_permission(self):
        assert get_cafe_workflow_grade(STEP_COMMENT_WRITE) == GRADE_USER_DELEGATED

    def test_cafe_post_edit_requires_permission(self):
        assert requires_permission("cafe_post_edit") is True

    def test_cafe_post_delete_requires_permission(self):
        assert requires_permission("cafe_post_delete") is True

    def test_cafe_comment_edit_requires_permission(self):
        assert requires_permission("cafe_comment_edit") is True

    def test_cafe_comment_delete_requires_permission(self):
        assert requires_permission("cafe_comment_delete") is True


class TestCafeReadDryRun:
    def test_search_cafe_dryrun(self):
        result = search_cafe("파이썬 스터디")
        assert result["ok"] is True
        assert "파이썬 스터디" in result.get("summary", "") or \
               "파이썬 스터디" in str(result.get("keywords", []))

    def test_read_cafe_post_dryrun(self):
        result = read_cafe_post("https://cafe.naver.com/test/123")
        assert result["ok"] is True
        assert "title" in result

    def test_cafe_read_safe_result(self):
        result = read_cafe_post("https://cafe.naver.com/test/123")
        violations = validate_naver_result(result)
        assert violations == []

    def test_cafe_search_safe_result(self):
        result = search_cafe("테스트")
        violations = validate_naver_result(result)
        assert violations == []

    def test_blog_material_from_post(self):
        post = read_cafe_post("https://cafe.naver.com/test/123")
        material = generate_blog_material_from_post(post)
        assert material["ok"] is True
        assert len(material["blog_material_candidates"]) > 0
        violations = validate_naver_result(material)
        assert violations == []


class TestCafeWritePermission:
    def test_write_without_permission_blocked(self):
        result = write_cafe_post(
            "cafe.naver.com", "게시글 내용입니다.", permission_id="",
        )
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_comment_without_permission_blocked(self):
        result = write_cafe_comment(
            "cafe.naver.com", "댓글 내용입니다.", permission_id="",
        )
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_write_with_permission_allowed(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        result = write_cafe_post(
            "cafe.naver.com",
            "카페 게시글 내용입니다.",
            permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_ALLOWED

    def test_comment_with_permission_allowed(self):
        perm = grant_permission("cafe_comment_write", "cafe.naver.com")
        result = write_cafe_comment(
            "cafe.naver.com",
            "카페 댓글 내용입니다.",
            permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_ALLOWED

    def test_write_result_safe(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        result = write_cafe_post(
            "cafe.naver.com", "게시글.", permission_id=perm["permission_id"],
        )
        violations = validate_naver_result(result.get("result", {}))
        assert violations == []

    def test_revoked_permission_blocked(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com")
        revoke(perm["permission_id"])
        result = write_cafe_post(
            "cafe.naver.com", "게시글.", permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_NEED_PERMISSION

    def test_expired_permission_blocked(self):
        perm = grant_permission("cafe_post_write", "cafe.naver.com", duration_seconds=0)
        import time; time.sleep(0.01)
        result = write_cafe_post(
            "cafe.naver.com", "게시글.", permission_id=perm["permission_id"],
        )
        assert result["status"] == EXEC_NEED_PERMISSION
