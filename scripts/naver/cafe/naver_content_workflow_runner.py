"""
네이버 카페→블로그 콘텐츠 workflow 통합 runner

카페 탐색 → 소재 추출 → 블로그 초안 → (권한 있으면) 발행
공통 LOCAL_PLAYWRIGHT task protocol만 사용.
서버 외부 브라우저 없음.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.agent_runtime.runtime.permission.delegated_action_executor import (
    EXEC_ALLOWED,
)
from scripts.naver.blog.naver_blog_workflow import (
    generate_blog_draft,
    publish_blog_post,
)
from scripts.naver.cafe.naver_cafe_workflow import (
    generate_blog_material_from_post,
    read_cafe_post,
    search_cafe,
)

# ── workflow 최종 상태 ─────────────────────────────────────────────────────────

WORKFLOW_PASS = "WORKFLOW_PASS"  # noqa: S105
WORKFLOW_WARN_AUTH = "WORKFLOW_WARN_AUTH_REQUIRED"
WORKFLOW_WARN_PERMISSION = "WORKFLOW_WARN_PERMISSION_REQUIRED"
WORKFLOW_FAIL = "WORKFLOW_FAIL"


def run_cafe_to_blog_workflow(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    cafe_url: str,
    cafe_search_query: str = "",
    blog_domain: str = "blog.naver.com",
    blog_permission_id: str | None = None,
    cafe_write_permission_id: str | None = None,
    cafe_comment_permission_id: str | None = None,
    blog_topic: str = "",
    runner_fn: Callable | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    카페 탐색 → 소재 추출 → 블로그 초안 → (권한 있으면) 발행.

    dry_run=True: 실제 발행 없이 초안/권한 확인만 수행.
    runner_fn: 실제 Playwright 실행 함수.
    """
    run_at = datetime.now(tz=UTC).isoformat()
    report: dict[str, Any] = {
        "run_at": run_at,
        "run_id": str(uuid.uuid4()),
        "cafe_url": cafe_url,
        "blog_domain": blog_domain,
        "dry_run": dry_run,
        "server_browser_used": False,
        "steps": [],
        "final_status": None,
        "blog_draft": None,
        "publish_result": None,
        "permission_required": [],
    }
    steps = report["steps"]

    # STEP A: 카페 탐색/읽기 (AUTO_ALLOWED)
    if cafe_search_query:
        search_result = search_cafe(cafe_search_query, cafe_url, runner_fn)
        steps.append({"step": "cafe_search", "ok": search_result.get("ok"), "query": cafe_search_query})

    post_result = read_cafe_post(cafe_url, runner_fn)
    steps.append(
        {
            "step": "cafe_read_post",
            "ok": post_result.get("ok"),
            "title": post_result.get("title", ""),
            "summary": post_result.get("summary", ""),
            "keywords": post_result.get("keywords", []),
        }
    )

    # STEP B: 소재 추출 (AUTO_ALLOWED)
    material = generate_blog_material_from_post(post_result)
    steps.append(
        {
            "step": "cafe_extract_material",
            "ok": material.get("ok"),
            "candidates_count": len(material.get("blog_material_candidates", [])),
        }
    )

    # STEP C: 블로그 초안 (AUTO_ALLOWED)
    topic = blog_topic or post_result.get("title", "네이버 카페 탐색 결과")
    draft = generate_blog_draft(
        topic=topic,
        source_material=material.get("blog_material_candidates", []),
        keywords=material.get("keywords", []),
    )
    report["blog_draft"] = draft
    steps.append(
        {
            "step": "blog_generate_draft",
            "ok": draft.get("ok"),
            "title_count": len(draft.get("title_candidates", [])),
            "tag_count": len(draft.get("tag_candidates", [])),
        }
    )

    # STEP D: 발행 (USER_DELEGATED_PERMISSION_REQUIRED)
    if dry_run:
        if not blog_permission_id:
            report["permission_required"].append("blog_publish")
        if not cafe_write_permission_id:
            report["permission_required"].append("cafe_post_write")
        if not cafe_comment_permission_id:
            report["permission_required"].append("cafe_comment_write")
        report["final_status"] = WORKFLOW_WARN_PERMISSION if report["permission_required"] else WORKFLOW_PASS
        return report

    # 실제 발행 시도
    if blog_permission_id:
        content = draft.get("body_draft", "")
        pub_result = publish_blog_post(
            content=content,
            permission_id=blog_permission_id,
            domain=blog_domain,
            approved_preview=content[:100],
            runner_fn=runner_fn,
        )
        report["publish_result"] = pub_result
        steps.append(
            {
                "step": "blog_publish",
                "status": pub_result.get("status"),
                "ok": pub_result.get("ok"),
            }
        )
        if pub_result.get("status") != EXEC_ALLOWED:
            report["permission_required"].append("blog_publish")
    else:
        report["permission_required"].append("blog_publish")

    if report["permission_required"]:
        report["final_status"] = WORKFLOW_WARN_PERMISSION
    else:
        report["final_status"] = WORKFLOW_PASS

    return report
