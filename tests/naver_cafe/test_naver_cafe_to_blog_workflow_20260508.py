"""
네이버 카페→블로그 통합 workflow 테스트
"""

import pytest

from core.agent_runtime.runtime.permission.delegated_action_executor import EXEC_ALLOWED
from core.agent_runtime.runtime.permission.delegated_permission_store import (
    clear_all,
    grant_permission,
    revoke,
)
from scripts.naver.blog.naver_content_safe_result import validate_naver_result
from scripts.naver.cafe.naver_content_workflow_runner import (
    WORKFLOW_WARN_PERMISSION,
    run_cafe_to_blog_workflow,
)


@pytest.fixture(autouse=True)
def reset():
    clear_all()
    yield
    clear_all()


class TestWorkflowDryRun:
    def test_dryrun_without_permission_warn(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            dry_run=True,
        )
        assert result["final_status"] == WORKFLOW_WARN_PERMISSION
        assert "blog_publish" in result["permission_required"]

    def test_dryrun_generates_blog_draft(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            dry_run=True,
        )
        draft = result.get("blog_draft")
        assert draft is not None
        assert draft["ok"] is True
        assert len(draft["title_candidates"]) >= 1

    def test_dryrun_server_browser_not_used(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            dry_run=True,
        )
        assert result["server_browser_used"] is False

    def test_dryrun_with_search_query(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            cafe_search_query="파이썬 스터디",
            dry_run=True,
        )
        step_names = [s["step"] for s in result["steps"]]
        assert "cafe_search" in step_names

    def test_steps_contain_cafe_read(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            dry_run=True,
        )
        step_names = [s["step"] for s in result["steps"]]
        assert "cafe_read_post" in step_names

    def test_steps_contain_blog_draft(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            dry_run=True,
        )
        step_names = [s["step"] for s in result["steps"]]
        assert "blog_generate_draft" in step_names


class TestWorkflowWithPermission:
    def test_workflow_with_blog_permission_pass(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            blog_permission_id=perm["permission_id"],
            dry_run=False,
        )
        assert result["publish_result"] is not None
        assert result["publish_result"]["status"] == EXEC_ALLOWED

    def test_workflow_no_sensitive_data_in_draft(self):
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            dry_run=True,
        )
        draft = result.get("blog_draft", {})
        violations = validate_naver_result(draft)
        assert violations == []

    def test_workflow_revoked_permission_handled(self):
        perm = grant_permission("blog_publish", "blog.naver.com")
        revoke(perm["permission_id"])
        result = run_cafe_to_blog_workflow(
            cafe_url="https://cafe.naver.com/test",
            blog_permission_id=perm["permission_id"],
            dry_run=False,
        )
        # 철회된 권한: publish_result status가 EXEC_NEED_PERMISSION
        pub = result.get("publish_result")
        if pub:
            from core.agent_runtime.runtime.permission.delegated_action_executor import EXEC_NEED_PERMISSION

            assert pub["status"] == EXEC_NEED_PERMISSION
