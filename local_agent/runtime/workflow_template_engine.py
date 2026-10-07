"""
Workflow Template Engine

업무 시나리오를 사이트별 하드코딩 없이 template으로 실행한다.
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_USER_DELEGATED,
)

# ── Template Step 구조 ────────────────────────────────────────────────────────


def _step(step_id: str, action: str, risk_level: str, optional: bool = False, description: str = "") -> dict[str, Any]:
    return {
        "step_id": step_id,
        "action": action,
        "risk_level": risk_level,
        "optional": optional,
        "description": description,
    }


def _template(
    workflow_id: str,
    display_name: str,
    steps: list[dict],
    applicable_categories: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "display_name": display_name,
        "steps": steps,
        "applicable_categories": applicable_categories or [],
        "description": description,
    }


# ── 등록된 Workflow Template ───────────────────────────────────────────────────

_TEMPLATES: dict[str, dict[str, Any]] = {
    "readonly_site_explore": _template(
        workflow_id="readonly_site_explore",
        display_name="사이트 read-only 탐색",
        steps=[
            _step("open", "open_url", GRADE_AUTO_ALLOWED),
            _step("read", "read_page", GRADE_AUTO_ALLOWED),
            _step("extract", "extract_text", GRADE_AUTO_ALLOWED),
            _step("screenshot", "capture_screenshot", GRADE_AUTO_ALLOWED, optional=True),
        ],
        description="사이트 공개 페이지를 read-only로 탐색한다.",
    ),
    "download_documents": _template(
        workflow_id="download_documents",
        display_name="문서 다운로드",
        steps=[
            _step("open", "open_url", GRADE_AUTO_ALLOWED),
            _step("search", "search", GRADE_AUTO_ALLOWED, optional=True),
            _step("extract_list", "extract_table", GRADE_AUTO_ALLOWED),
            _step("download", "download_file", GRADE_AUTO_ALLOWED),
        ],
        description="공개 문서를 다운로드한다.",
    ),
    "content_research_summary": _template(
        workflow_id="content_research_summary",
        display_name="콘텐츠 리서치 및 요약",
        steps=[
            _step("search", "search", GRADE_AUTO_ALLOWED),
            _step("read", "extract_text", GRADE_AUTO_ALLOWED),
            _step("summarize", "summarize", GRADE_AUTO_ALLOWED),
            _step("draft", "generate_draft", GRADE_AUTO_ALLOWED),
        ],
        description="여러 소스를 탐색하고 요약 및 초안을 생성한다.",
    ),
    "cafe_to_blog_draft": _template(
        workflow_id="cafe_to_blog_draft",
        display_name="카페→블로그 초안",
        steps=[
            _step("cafe_search", "search", GRADE_AUTO_ALLOWED),
            _step("cafe_read", "extract_text", GRADE_AUTO_ALLOWED),
            _step("summarize", "summarize", GRADE_AUTO_ALLOWED, optional=True),
            _step("generate", "generate_draft", GRADE_AUTO_ALLOWED),
            _step("save_draft", "save_draft", GRADE_AUTO_ALLOWED, optional=True),
        ],
        description="카페 콘텐츠 탐색 후 블로그 초안 생성.",
    ),
    "blog_publish_with_permission": _template(
        workflow_id="blog_publish_with_permission",
        display_name="블로그 발행 (권한 필요)",
        steps=[
            _step("draft", "generate_draft", GRADE_AUTO_ALLOWED, optional=True),
            _step("preview", "preview", GRADE_AUTO_ALLOWED, optional=True),
            _step("publish", "blog_publish", GRADE_USER_DELEGATED),
        ],
        description="사용자 위임 권한으로 블로그 발행.",
    ),
    "comment_with_permission": _template(
        workflow_id="comment_with_permission",
        display_name="댓글 작성 (권한 필요)",
        steps=[
            _step("read", "read_page", GRADE_AUTO_ALLOWED),
            _step("comment", "cafe_comment_write", GRADE_USER_DELEGATED),
        ],
        description="사용자 위임 권한으로 댓글 작성.",
    ),
    "generic_form_fill_preview": _template(
        workflow_id="generic_form_fill_preview",
        display_name="폼 작성 미리보기",
        steps=[
            _step("open", "open_url", GRADE_AUTO_ALLOWED),
            _step("fill", "fill_non_sensitive_form", GRADE_AUTO_ALLOWED),
            _step("preview", "preview", GRADE_AUTO_ALLOWED),
            _step("submit", "submit_non_legal_form", GRADE_USER_DELEGATED),
        ],
        description="비민감 폼 작성 및 제출.",
    ),
    "government_readonly_status_check": _template(
        workflow_id="government_readonly_status_check",
        display_name="정부 사이트 상태 조회",
        steps=[
            _step("open", "open_url", GRADE_AUTO_ALLOWED),
            _step("search", "search", GRADE_AUTO_ALLOWED, optional=True),
            _step("extract", "extract_text", GRADE_AUTO_ALLOWED),
            _step("download", "download_file", GRADE_AUTO_ALLOWED, optional=True),
        ],
        description="정부 사이트 공개 정보 read-only 조회.",
    ),
    "financial_readonly_statement_download": _template(
        workflow_id="financial_readonly_statement_download",
        display_name="금융 명세서 다운로드",
        steps=[
            _step("open", "open_url", GRADE_AUTO_ALLOWED),
            _step("login_wait", "detect_login_status", GRADE_AUTO_ALLOWED),
            _step("extract", "extract_table", GRADE_AUTO_ALLOWED),
            _step("download", "download_file", GRADE_AUTO_ALLOWED),
        ],
        description="금융 사이트 명세서 read-only 다운로드.",
    ),
    "ecommerce_order_status_readonly": _template(
        workflow_id="ecommerce_order_status_readonly",
        display_name="주문 상태 조회",
        steps=[
            _step("open", "open_url", GRADE_AUTO_ALLOWED),
            _step("extract", "extract_table", GRADE_AUTO_ALLOWED),
            _step("summarize", "summarize", GRADE_AUTO_ALLOWED, optional=True),
        ],
        description="주문/배송 상태 read-only 조회.",
    ),
}


def get_template(workflow_id: str) -> dict[str, Any] | None:
    return dict(_TEMPLATES[workflow_id]) if workflow_id in _TEMPLATES else None


def get_all_workflow_ids() -> list[str]:
    return list(_TEMPLATES.keys())


def is_template_registered(workflow_id: str) -> bool:
    return workflow_id in _TEMPLATES


def get_step_risk_level(workflow_id: str, step_id: str) -> str | None:
    """특정 step의 risk_level 반환."""
    tmpl = get_template(workflow_id)
    if not tmpl:
        return None
    for step in tmpl["steps"]:
        if step["step_id"] == step_id:
            return step["risk_level"]
    return None


def get_delegated_steps(workflow_id: str) -> list[dict[str, Any]]:
    """USER_DELEGATED_PERMISSION_REQUIRED 단계 목록 반환."""
    tmpl = get_template(workflow_id)
    if not tmpl:
        return []
    return [s for s in tmpl["steps"] if s["risk_level"] == GRADE_USER_DELEGATED]


def get_auto_steps(workflow_id: str) -> list[dict[str, Any]]:
    """AUTO_ALLOWED 단계 목록 반환."""
    tmpl = get_template(workflow_id)
    if not tmpl:
        return []
    return [s for s in tmpl["steps"] if s["risk_level"] == GRADE_AUTO_ALLOWED]


def register_template(template: dict[str, Any]) -> None:
    """workflow template을 등록한다."""
    wid = (template.get("workflow_id") or "").strip()
    if not wid:
        raise ValueError("workflow_id 필수")
    if "steps" not in template or not template["steps"]:
        raise ValueError("steps 필수")
    _TEMPLATES[wid] = dict(template)
