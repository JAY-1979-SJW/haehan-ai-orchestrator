"""
콘텐츠 발행 guard

발행 전 승인 내용과 실제 발행 내용이 일치하는지 검증.
스팸성 대량 게시/댓글 차단.
"""
from __future__ import annotations

from typing import Any

# ── 스팸 임계값 ────────────────────────────────────────────────────────────────

MAX_COMMENTS_PER_GRANT = 20   # 단일 권한으로 작성 가능한 최대 댓글 수
MAX_POSTS_PER_GRANT = 5       # 단일 권한으로 작성 가능한 최대 게시글 수
MIN_CONTENT_LENGTH = 5        # 최소 콘텐츠 길이 (빈 글 방지)
MAX_CONTENT_LENGTH = 100_000  # 최대 콘텐츠 길이

# ── 스팸 감지 키워드 패턴 ─────────────────────────────────────────────────────

_SPAM_SIGNALS = (
    "홍보", "광고", "클릭", "무료", "수익", "바이럴",
    "spam", "click here", "make money",
)


def check_content_matches_approval(
    approved_preview: str,
    actual_content: str,
    strict: bool = False,
) -> dict[str, Any]:
    """
    승인된 preview와 실제 발행 내용이 일치하는지 확인한다.

    strict=False: preview가 actual_content에 포함되면 OK
    strict=True: 정확히 일치
    """
    if not approved_preview:
        return {"match": True, "reason": "preview 없음 (검증 생략)"}

    if strict:
        match = approved_preview.strip() == actual_content.strip()
    else:
        match = approved_preview.strip() in actual_content

    if not match:
        return {
            "match": False,
            "reason": f"승인 내용과 실제 발행 내용 불일치. approved_preview={approved_preview[:50]!r}",
        }
    return {"match": True, "reason": "OK"}


def check_bulk_spam(
    action: str,
    request_count: int,
    max_executions: int,
) -> dict[str, Any]:
    """
    스팸성 대량 게시/댓글 여부를 검사한다.

    반환: {"allowed": bool, "reason": str}
    """
    comment_actions = {"cafe_comment_write", "cafe_comment_edit", "cafe_comment_delete"}
    post_actions = {"blog_publish", "cafe_post_write", "blog_edit", "cafe_post_edit"}

    if action in comment_actions and request_count > MAX_COMMENTS_PER_GRANT:
        return {
            "allowed": False,
            "reason": f"스팸 차단: 댓글 요청 수({request_count}) > 최대 허용({MAX_COMMENTS_PER_GRANT})",
        }
    if action in post_actions and request_count > MAX_POSTS_PER_GRANT:
        return {
            "allowed": False,
            "reason": f"스팸 차단: 게시 요청 수({request_count}) > 최대 허용({MAX_POSTS_PER_GRANT})",
        }
    if max_executions > 50:
        return {
            "allowed": False,
            "reason": f"스팸 차단: max_executions({max_executions}) > 상한(50)",
        }

    return {"allowed": True, "reason": "OK"}


def check_content_policy(content: str) -> dict[str, Any]:
    """
    콘텐츠 기본 정책 검사.

    반환: {"allowed": bool, "reason": str, "spam_signal": bool}
    """
    if len(content) < MIN_CONTENT_LENGTH:
        return {"allowed": False, "reason": "콘텐츠가 너무 짧음", "spam_signal": False}
    if len(content) > MAX_CONTENT_LENGTH:
        return {"allowed": False, "reason": f"콘텐츠 길이 초과({len(content)} > {MAX_CONTENT_LENGTH})", "spam_signal": False}

    spam_signal = any(kw in content for kw in _SPAM_SIGNALS)
    return {"allowed": True, "reason": "OK", "spam_signal": spam_signal}


def validate_publish_request(
    action: str,
    domain: str,
    content: str,
    approved_preview: str = "",
    request_count: int = 1,
    max_executions: int = 1,
) -> dict[str, Any]:
    """
    발행 요청 통합 검증.

    반환: {"allowed": bool, "reason": str, "violations": list[str]}
    """
    violations: list[str] = []

    content_check = check_content_policy(content)
    if not content_check["allowed"]:
        violations.append(content_check["reason"])

    spam_check = check_bulk_spam(action, request_count, max_executions)
    if not spam_check["allowed"]:
        violations.append(spam_check["reason"])

    if approved_preview:
        match_check = check_content_matches_approval(approved_preview, content)
        if not match_check["match"]:
            violations.append(match_check["reason"])

    return {
        "allowed": len(violations) == 0,
        "reason": "; ".join(violations) if violations else "OK",
        "violations": violations,
        "spam_signal": content_check.get("spam_signal", False),
    }
