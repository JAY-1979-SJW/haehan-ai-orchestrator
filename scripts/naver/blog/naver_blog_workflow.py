"""
네이버 블로그 workflow

공통 LOCAL_PLAYWRIGHT task protocol 사용.
블로그 전용 로그인 자동화 없음.
초안/임시저장: AUTO_ALLOWED
발행/수정/삭제: USER_DELEGATED_PERMISSION_REQUIRED
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
    build_blog_draft_result,
    sanitize_naver_result,
)

# ── 블로그 workflow 단계 상수 ─────────────────────────────────────────────────

STEP_GENERATE_TITLE = "blog_generate_title"
STEP_GENERATE_BODY = "blog_generate_body"
STEP_GENERATE_TAGS = "blog_generate_tags"
STEP_PREVIEW = "blog_preview"
STEP_SAVE_DRAFT = "blog_save_draft"
STEP_PUBLISH = "blog_publish"
STEP_SCHEDULE_PUBLISH = "blog_schedule_publish"
STEP_EDIT = "blog_edit"
STEP_DELETE = "blog_delete"
STEP_SET_VISIBILITY = "blog_set_visibility"


def generate_blog_draft(
    topic: str,
    source_material: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """
    블로그 초안 생성. AUTO_ALLOWED.
    실제 LLM 없이 구조화된 초안 반환.
    민감값 없음.
    """
    source = source_material or []
    kws = keywords or []

    title_candidates = [
        f"{topic} 완전 정리",
        f"{topic}에 대한 모든 것",
        f"[정보] {topic} 핵심 요약",
    ]
    tag_candidates = kws[:5] if kws else [topic, "정보", "요약"]

    body_lines = [f"# {topic}"]
    if source:
        body_lines.append("\n## 참고 자료")
        for s in source[:3]:
            body_lines.append(f"- {s}")
    body_lines.append("\n## 본문")
    body_lines.append(f"{topic}에 관한 블로그 초안입니다. 내용을 채워주세요.")
    if kws:
        body_lines.append("\n## 키워드")
        body_lines.append(", ".join(kws[:5]))

    return build_blog_draft_result(
        task_id=str(uuid.uuid4()),
        title_candidates=title_candidates,
        body_draft="\n".join(body_lines),
        tag_candidates=tag_candidates,
        source_urls=source[:5],
        ok=True,
        message_ko=f"블로그 초안 생성 완료: {topic}",
    )


def publish_blog_post(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    content: str,
    permission_id: str,
    domain: str = "blog.naver.com",
    approved_preview: str = "",
    account: str = "",
    task_scope: str = "",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    블로그 발행. USER_DELEGATED_PERMISSION_REQUIRED.
    권한 없으면 EXEC_NEED_PERMISSION 반환.
    """
    return execute_delegated_action(
        action="blog_publish",
        domain=domain,
        permission_id=permission_id,
        content=content,
        approved_preview=approved_preview,
        account=account,
        task_scope=task_scope,
        runner_fn=runner_fn,
    )


def schedule_blog_publish(
    content: str,
    permission_id: str,
    domain: str = "blog.naver.com",
    approved_preview: str = "",
    account: str = "",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    블로그 예약 발행. USER_DELEGATED_PERMISSION_REQUIRED.
    """
    return execute_delegated_action(
        action="blog_schedule_publish",
        domain=domain,
        permission_id=permission_id,
        content=content,
        approved_preview=approved_preview,
        account=account,
        runner_fn=runner_fn,
    )


def edit_blog_post(
    content: str,
    permission_id: str,
    domain: str = "blog.naver.com",
    account: str = "",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """블로그 수정. USER_DELEGATED_PERMISSION_REQUIRED."""
    return execute_delegated_action(
        action="blog_edit",
        domain=domain,
        permission_id=permission_id,
        content=content,
        account=account,
        runner_fn=runner_fn,
    )


def delete_blog_post(
    permission_id: str,
    domain: str = "blog.naver.com",
    account: str = "",
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """블로그 삭제. USER_DELEGATED_PERMISSION_REQUIRED."""
    return execute_delegated_action(
        action="blog_delete",
        domain=domain,
        permission_id=permission_id,
        content="삭제 요청",
        account=account,
        runner_fn=runner_fn,
    )


def read_blog_post(
    post_url: str,
    runner_fn: Callable | None = None,
) -> dict[str, Any]:
    """블로그 게시글 읽기. AUTO_ALLOWED."""
    task = build_task(
        action="extract_text",
        target_url=post_url,
        domain="blog.naver.com",
        readonly=True,
        task_id=str(uuid.uuid4()),
        metadata={"workflow_step": STEP_GENERATE_BODY},
    )
    if runner_fn:
        raw = runner_fn(task)
        return sanitize_naver_result(raw)
    return {
        "task_id": task["task_id"],
        "url": post_url,
        "title": "블로그 게시글 (dry-run)",
        "body_text_sample": "블로그 본문 샘플.",
        "ok": True,
        "message_ko": "블로그 게시글 읽기 dry-run.",
        "sensitive_data_collected": False,
        "cookie_exported": False,
        "session_exported": False,
        "password_collected": False,
        "otp_collected": False,
        "certificate_password_collected": False,
        "storage_state_exported": False,
        "server_browser_used": False,
    }


def get_blog_workflow_grade(step: str) -> str:
    """블로그 workflow 단계의 실행 등급 반환."""
    from core.agent_runtime.runtime.permission.content_workflow_policy import get_workflow_grade

    return get_workflow_grade(step)
