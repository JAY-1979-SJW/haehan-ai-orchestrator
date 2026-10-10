"""
콘텐츠 발행 guard 테스트
"""

from core.agent_runtime.runtime.permission.content_publish_guard import (
    MAX_COMMENTS_PER_GRANT,
    MAX_POSTS_PER_GRANT,
    check_bulk_spam,
    check_content_matches_approval,
    check_content_policy,
    validate_publish_request,
)


class TestContentMatchesApproval:
    def test_matching_content_ok(self):
        result = check_content_matches_approval("블로그 게시글", "블로그 게시글 전체 내용입니다.")
        assert result["match"] is True

    def test_mismatched_content_rejected(self):
        result = check_content_matches_approval("승인된 내용", "전혀 다른 내용")
        assert result["match"] is False

    def test_empty_preview_skips_check(self):
        result = check_content_matches_approval("", "아무 내용이나")
        assert result["match"] is True

    def test_strict_mode_exact_match(self):
        result = check_content_matches_approval("정확한 내용", "정확한 내용", strict=True)
        assert result["match"] is True

    def test_strict_mode_partial_rejected(self):
        result = check_content_matches_approval("정확한 내용", "정확한 내용 + 추가 텍스트", strict=True)
        assert result["match"] is False


class TestBulkSpamCheck:
    def test_comment_count_within_limit(self):
        result = check_bulk_spam("cafe_comment_write", MAX_COMMENTS_PER_GRANT, MAX_COMMENTS_PER_GRANT)
        assert result["allowed"] is True

    def test_comment_count_exceeds_limit(self):
        result = check_bulk_spam("cafe_comment_write", MAX_COMMENTS_PER_GRANT + 1, MAX_COMMENTS_PER_GRANT + 1)
        assert result["allowed"] is False
        assert "스팸 차단" in result["reason"]

    def test_post_count_within_limit(self):
        result = check_bulk_spam("blog_publish", MAX_POSTS_PER_GRANT, MAX_POSTS_PER_GRANT)
        assert result["allowed"] is True

    def test_post_count_exceeds_limit(self):
        result = check_bulk_spam("blog_publish", MAX_POSTS_PER_GRANT + 1, MAX_POSTS_PER_GRANT + 1)
        assert result["allowed"] is False

    def test_max_executions_over_50_blocked(self):
        result = check_bulk_spam("cafe_comment_write", 10, 51)
        assert result["allowed"] is False
        assert "상한" in result["reason"]


class TestContentPolicy:
    def test_normal_content_allowed(self):
        result = check_content_policy("정상적인 블로그 게시글 내용입니다.")
        assert result["allowed"] is True
        assert result["spam_signal"] is False

    def test_too_short_blocked(self):
        result = check_content_policy("짧")
        assert result["allowed"] is False

    def test_empty_blocked(self):
        result = check_content_policy("")
        assert result["allowed"] is False

    def test_spam_signal_detected(self):
        result = check_content_policy("무료 홍보 클릭하세요.")
        assert result["allowed"] is True
        assert result["spam_signal"] is True


class TestValidatePublishRequest:
    def test_valid_blog_publish_allowed(self):
        result = validate_publish_request(
            action="blog_publish",
            domain="blog.naver.com",
            content="정상적인 블로그 게시글입니다.",
            approved_preview="정상적인 블로그",
            request_count=1,
            max_executions=1,
        )
        assert result["allowed"] is True
        assert result["violations"] == []

    def test_content_mismatch_rejected(self):
        result = validate_publish_request(
            action="blog_publish",
            domain="blog.naver.com",
            content="전혀 다른 내용",
            approved_preview="승인된 내용",
        )
        assert result["allowed"] is False
        assert len(result["violations"]) > 0

    def test_bulk_comment_spam_rejected(self):
        result = validate_publish_request(
            action="cafe_comment_write",
            domain="cafe.naver.com",
            content="댓글 내용입니다.",
            request_count=MAX_COMMENTS_PER_GRANT + 1,
            max_executions=MAX_COMMENTS_PER_GRANT + 1,
        )
        assert result["allowed"] is False
        assert any("스팸" in v for v in result["violations"])

    def test_bulk_post_spam_rejected(self):
        result = validate_publish_request(
            action="blog_publish",
            domain="blog.naver.com",
            content="블로그 글입니다.",
            request_count=MAX_POSTS_PER_GRANT + 1,
            max_executions=MAX_POSTS_PER_GRANT + 1,
        )
        assert result["allowed"] is False

    def test_cafe_post_normal_allowed(self):
        result = validate_publish_request(
            action="cafe_post_write",
            domain="cafe.naver.com",
            content="카페에 올릴 정상 게시글입니다.",
        )
        assert result["allowed"] is True
