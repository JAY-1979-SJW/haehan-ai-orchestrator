"""Universal AI Site Agent — 전체 orchestration."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    GRADE_AUTO_ALLOWED,
)
from core.agent_runtime.runtime.site_profile.site_type_classifier import classify_site
from core.agent_runtime.runtime.universal.generic_selector_discovery import discover_selectors
from core.agent_runtime.runtime.universal.learned_site_profile_store import (
    has_learned_profile,
    save_learned_profile,
)
from core.agent_runtime.runtime.universal.universal_page_observer import observe_page_from_dict
from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_WARN_AUTH,
    STATUS_WARN_PERMISSION,
    build_universal_result,
)
from core.agent_runtime.runtime.universal.universal_task_planner import create_plan, get_auto_only_plan
from core.agent_runtime.runtime.universal.user_intent_parser import parse_intent

# 안전 경계 — 항상 False
_AGENT_SAFE_FIELDS = {
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "storage_state_exported": False,
    "server_browser_used": False,
}


def _build_agent_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    site_id: str,
    status: str,
    actions_executed: list[str],
    pending_permission: list[str],
    user_direct_required: list[str],
    blocked: list[str],
    safe_outputs: dict[str, Any],
    audit_log_ids: list[str],
    message_ko: str = "",
) -> dict[str, Any]:
    result = build_universal_result(
        task_id=task_id,
        site_id=site_id,
        workflow_id="universal_ai_site_agent",
        status=status,
        actions_executed=actions_executed,
        actions_pending_permission=pending_permission,
        actions_user_direct_required=user_direct_required,
        blocked_actions=blocked,
        safe_outputs=safe_outputs,
        audit_log_ids=audit_log_ids,
        message_ko=message_ko,
    )
    result.update(_AGENT_SAFE_FIELDS)
    return result


def run_agent(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    instruction: str,
    page_data: dict[str, Any],
    permission_map: dict[str, bool] | None = None,
    runner_fn: Callable | None = None,
    task_id: str | None = None,
    dry_run: bool = False,
    save_learned: bool = True,
) -> dict[str, Any]:
    """
    사용자 자연어 지시 + 현재 페이지 데이터를 받아 agent를 실행한다.

    page_data 예:
    {
      "url": "https://...",
      "title": "...",
      "text_content": "...",
      "buttons": [...],
      "links": [...],
      "form_labels": [...],
      "heading_texts": [...],
    }
    """
    task_id = task_id or str(uuid.uuid4())
    permission_map = permission_map or {}
    audit_log_ids: list[str] = []
    actions_executed: list[str] = []

    # STEP 1: 페이지 관찰
    observation = observe_page_from_dict(page_data)
    host = observation.get("host", "unknown")

    # STEP 2: intent 파싱
    intent_result = parse_intent(instruction)
    intent = intent_result["intent"]

    # STEP 3: 사이트 유형 분류
    obs_with_text = dict(observation)
    obs_with_text["text_content"] = page_data.get("text_content", "")
    site_classification = classify_site(obs_with_text)
    site_type = site_classification.get("site_type", "unknown")
    matched_profile = site_classification.get("matched_profile_id") or "generic_content_site"

    # STEP 4: selector 발견
    selectors = discover_selectors(observation)

    # STEP 5: 실행 계획 생성
    plan = create_plan(
        intent_result=intent_result,
        observation=observation,
        site_classification=site_classification,
        has_permissions=permission_map,
    )

    # STEP 6: BLOCKED action 확인
    if plan.get("blocked"):
        return _build_agent_result(
            task_id=task_id,
            site_id=matched_profile,
            status=STATUS_BLOCKED,
            actions_executed=[],
            pending_permission=[],
            user_direct_required=[],
            blocked=plan["blocked"],
            safe_outputs={},
            audit_log_ids=audit_log_ids,
            message_ko=f"BLOCKED action 포함: {plan['blocked']}",
        )

    # STEP 7: USER_DIRECT_REQUIRED 확인
    if plan.get("user_direct_required"):
        return _build_agent_result(
            task_id=task_id,
            site_id=matched_profile,
            status=STATUS_WARN_AUTH,
            actions_executed=[],
            pending_permission=[],
            user_direct_required=plan["user_direct_required"],
            blocked=[],
            safe_outputs={},
            audit_log_ids=audit_log_ids,
            message_ko=f"사용자 직접 조작 필요: {plan['user_direct_required']}",
        )

    # STEP 8: PERMISSION_REQUIRED 확인
    if plan.get("pending_permission"):
        return _build_agent_result(
            task_id=task_id,
            site_id=matched_profile,
            status=STATUS_WARN_PERMISSION,
            actions_executed=[],
            pending_permission=plan["pending_permission"],
            user_direct_required=[],
            blocked=[],
            safe_outputs={},
            audit_log_ids=audit_log_ids,
            message_ko=f"권한 필요: {plan['pending_permission']}",
        )

    # STEP 9: AUTO_ALLOWED step 실행
    auto_steps = get_auto_only_plan(plan)
    step_outputs: dict[str, Any] = {
        "observation": {
            "host": host,
            "title": observation.get("title"),
            "page_type": observation.get("page_type_candidates"),
        },
        "intent": intent,
        "site_type": site_type,
        "selectors_discovered": {
            "has_search": bool(selectors.get("search_box")),
            "has_download": bool(selectors.get("download_links")),
            "has_forms": bool(selectors.get("title_input")),
            "risk_buttons": selectors.get("risk_buttons_detected", []),
        },
        "plan_summary": {
            "total_steps": len(plan["steps"]),
            "auto_steps": len(auto_steps),
        },
    }

    if not dry_run and runner_fn:
        for step in auto_steps:
            try:
                step_result = runner_fn(step["action"], domain=host)  # noqa: F841
                actions_executed.append(step["action"])
                log_id = str(uuid.uuid4())[:8]
                audit_log_ids.append(log_id)
            except Exception as e:  # noqa: BLE001 - 범용 사이트 자동화 에이전트 -- 액션 실행 실패는 즉시 STATUS_FAILED 결과로 반환(fail-closed)
                return _build_agent_result(
                    task_id=task_id,
                    site_id=matched_profile,
                    status=STATUS_FAILED,
                    actions_executed=actions_executed,
                    pending_permission=[],
                    user_direct_required=[],
                    blocked=[],
                    safe_outputs=step_outputs,
                    audit_log_ids=audit_log_ids,
                    message_ko=f"실행 오류: {e}",
                )
    else:
        # dry_run 또는 runner_fn 없음 → auto step 목록만 기록
        actions_executed = [s["action"] for s in auto_steps]
        audit_log_ids.append(str(uuid.uuid4())[:8])

    # STEP 10: learned profile 저장
    if save_learned and auto_steps:
        with suppress(Exception):
            _update_learned_profile(host, site_type, plan, selectors)

    return _build_agent_result(
        task_id=task_id,
        site_id=matched_profile,
        status=STATUS_COMPLETED,
        actions_executed=actions_executed,
        pending_permission=[],
        user_direct_required=[],
        blocked=[],
        safe_outputs=step_outputs,
        audit_log_ids=audit_log_ids,
        message_ko="완료",
    )


def _update_learned_profile(
    host: str,
    site_type: str,
    plan: dict[str, Any],
    selectors: dict[str, Any],
) -> None:
    """성공한 구조를 learned profile에 저장."""
    safe_selectors = {
        k: v
        for k, v in selectors.items()
        if k
        not in (
            "password_selector_discovered",
            "otp_selector_discovered",
            "cert_password_selector_discovered",
            "npki_selector_discovered",
        )
        and isinstance(v, list)
    }
    if not has_learned_profile(host):
        save_learned_profile(
            host=host,
            site_type=site_type,
            workflow_template_id=None,
            safe_selector_candidates=safe_selectors,
            capability_hints=[s["action"] for s in plan.get("steps", []) if s.get("risk") == GRADE_AUTO_ALLOWED],
            action_risk_mapping={s["action"]: s["risk"] for s in plan.get("steps", [])},
        )
    else:
        from core.agent_runtime.runtime.universal.learned_site_profile_store import update_learned_profile

        update_learned_profile(
            host,
            {
                "site_type": site_type,
                "last_successful_actions": [s["action"] for s in plan.get("steps", []) if s.get("executable")],
            },
        )
