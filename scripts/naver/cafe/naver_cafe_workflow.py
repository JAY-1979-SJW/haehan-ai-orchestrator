"""
네이버 카페 workflow

공통 LOCAL_PLAYWRIGHT task protocol 사용.
카페 전용 브라우저 도구/로그인 자동화 없음.
탐색/읽기: AUTO_ALLOWED (권한 불필요)
글쓰기/댓글: USER_DELEGATED_PERMISSION_REQUIRED
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from ai_orchestrator.contracts.local_task_protocol import (
    build_task,
)
from core.agent_runtime.runtime.permission.delegated_action_executor import (
    execute_delegated_action,
)
from scripts.naver.blog.naver_content_safe_result import (
    build_cafe_read_result,
    sanitize_naver_result,
)

# ── 카페 workflow 상태 상수 ───────────────────────────────────────────────────

STEP_SEARCH = "cafe_search"
STEP_READ_LIST = "cafe_read_list"
STEP_READ_POST = "cafe_read_post"
STEP_EXTRACT_SUMMARY = "cafe_extract_summary"
STEP_EXTRACT_KEYWORDS = "cafe_extract_keywords"
STEP_GENERATE_COMMENT_CANDIDATE = "cafe_generate_comment_candidate"
STEP_GENERATE_DRAFT = "cafe_generate_draft"
STEP_POST_WRITE = "cafe_post_write"
STEP_COMMENT_WRITE = "cafe_comment_write"
STEP_POST_EDIT = "cafe_post_edit"
STEP_POST_DELETE = "cafe_post_delete"


def search_cafe(
    query: str,
    cafe_url: str = "https://cafe.naver.com/",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    카페 검색. AUTO_ALLOWED.
    runner_fn: 실제 Playwright 실행 함수 (None이면 dry-run).
    """
    task = build_task(
        action="search",
        target_url=cafe_url,
        domain="cafe.naver.com",
        readonly=True,
        task_id=str(uuid.uuid4()),
        metadata={"query": query, "workflow_step": STEP_SEARCH},
    )

    if runner_fn:
        raw = runner_fn(task)
        return sanitize_naver_result(raw)

    return build_cafe_read_result(
        task_id=task["task_id"],
        url=cafe_url,
        summary=f"검색어: {query}",
        keywords=[query],
        ok=True,
        message_ko=f"카페 검색 dry-run: {query}",
    )


def read_cafe_post(
    post_url: str,
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    카페 게시글 읽기. AUTO_ALLOWED.
    제목/본문/작성일/URL 추출. 민감값 없음.
    """
    task = build_task(
        action="extract_text",
        target_url=post_url,
        domain="cafe.naver.com",
        readonly=True,
        task_id=str(uuid.uuid4()),
        metadata={"workflow_step": STEP_READ_POST},
    )

    if runner_fn:
        raw = runner_fn(task)
        return sanitize_naver_result(raw)

    return build_cafe_read_result(
        task_id=task["task_id"],
        url=post_url,
        title="카페 게시글 제목 (dry-run)",
        body_text="카페 게시글 본문 샘플입니다.",
        summary="요약: 카페 게시글 내용.",
        keywords=["카페", "게시글"],
        blog_material_candidates=["블로그 소재 후보"],
        comment_candidates=["댓글 후보 1"],
        ok=True,
        message_ko="카페 게시글 읽기 dry-run 완료.",
    )


def generate_blog_material_from_post(post_result: dict[str, Any]) -> dict[str, Any]:
    """
    카페 읽기 결과 → 블로그 소재 후보 생성. AUTO_ALLOWED.
    실제 LLM 호출 없이 구조화된 후보 반환.
    민감값 없음.
    """
    title = post_result.get("title", "")
    summary = post_result.get("summary", "")
    keywords = post_result.get("keywords", [])

    candidates = []
    if title:
        candidates.append(f"[카페 참고] {title}")
    if summary:
        candidates.append(f"[요약 기반] {summary[:100]}")
    for kw in keywords[:3]:
        candidates.append(f"[키워드 확장] {kw} 관련 블로그 주제")

    result = {
        "task_id": post_result.get("task_id", str(uuid.uuid4())),
        "source_url": post_result.get("url", ""),
        "blog_material_candidates": candidates,
        "keywords": keywords,
        "ok": True,
        "message_ko": "블로그 소재 후보 생성 완료.",
    }
    from scripts.naver.blog.naver_content_safe_result import _FIXED_SAFE_FIELDS

    result.update(_FIXED_SAFE_FIELDS)
    return result


def write_cafe_post(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    domain: str,
    content: str,
    permission_id: str,
    approved_preview: str = "",
    account: str = "",
    task_scope: str = "",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    카페 글쓰기. USER_DELEGATED_PERMISSION_REQUIRED.
    권한 없으면 EXEC_NEED_PERMISSION 반환.
    """
    return execute_delegated_action(
        action="cafe_post_write",
        domain=domain,
        permission_id=permission_id,
        content=content,
        approved_preview=approved_preview,
        account=account,
        task_scope=task_scope,
        runner_fn=runner_fn,
    )


def write_cafe_comment(
    domain: str,
    content: str,
    permission_id: str,
    approved_preview: str = "",
    account: str = "",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    카페 댓글 작성. USER_DELEGATED_PERMISSION_REQUIRED.
    권한 없으면 EXEC_NEED_PERMISSION 반환.
    """
    return execute_delegated_action(
        action="cafe_comment_write",
        domain=domain,
        permission_id=permission_id,
        content=content,
        approved_preview=approved_preview,
        account=account,
        runner_fn=runner_fn,
    )


def get_cafe_workflow_grade(step: str) -> str:
    """카페 workflow 단계의 실행 등급 반환."""
    from core.agent_runtime.runtime.permission.content_workflow_policy import get_workflow_grade

    return get_workflow_grade(step)
