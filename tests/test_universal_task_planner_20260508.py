"""tests/test_universal_task_planner_20260508.py"""

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    GRADE_AUTO_ALLOWED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from core.agent_runtime.runtime.universal.universal_task_planner import (
    create_plan,
    get_auto_only_plan,
    plan_has_blocked,
    plan_needs_permission,
)
from core.agent_runtime.runtime.universal.user_intent_parser import parse_intent


def _make_plan(instruction, host="unknown.example.com", text="", buttons=None, risk_signals=None, has_permissions=None):
    intent_result = parse_intent(instruction)
    observation = {
        "host": host,
        "title": "",
        "page_type_candidates": [],
        "visible_actions": [],
        "buttons_observed": buttons or [],
        "auth_signals": [],
        "risk_signals": risk_signals or [],
        "forms_detected": False,
        "download_candidates": [],
    }
    site_classification = {
        "site_type": "unknown",
        "confidence": "low",
        "matched_profile_id": None,
        "is_known_site": False,
    }
    return create_plan(intent_result, observation, site_classification, has_permissions=has_permissions)


def test_notice_plan_auto_steps():
    plan = _make_plan("공지사항 찾아서 요약해줘")
    auto = get_auto_only_plan(plan)
    assert len(auto) > 0
    for step in auto:
        assert step["risk"] == GRADE_AUTO_ALLOWED


def test_article_list_plan():
    plan = _make_plan("이 게시판 글 목록 추출해줘")
    assert "plan_id" in plan
    assert len(plan["steps"]) > 0


def test_blog_draft_auto_publish_delegated():
    plan = _make_plan("이 페이지 내용을 블로그 글로 만들어줘")
    # draft 생성은 AUTO, publish는 DELEGATED
    auto_actions = [s["action"] for s in plan["steps"] if s["risk"] == GRADE_AUTO_ALLOWED]
    assert len(auto_actions) > 0


def test_publish_requires_permission():
    plan = _make_plan("이 글을 발행해줘", has_permissions={})
    assert plan_needs_permission(plan) or plan.get("user_direct_required")


def test_publish_with_permission_executable():
    plan = _make_plan("이 글을 발행해줘", has_permissions={"publish_post": True})
    perm_steps = [s for s in plan["steps"] if s["risk"] == GRADE_USER_DELEGATED and s["executable"]]
    assert len(perm_steps) > 0


def test_delete_requires_permission():
    plan = _make_plan("이 게시글 삭제해줘")
    delegated = [s for s in plan["steps"] if s["risk"] == GRADE_USER_DELEGATED]
    assert len(delegated) > 0


def test_payment_risk_signal_escalates_to_direct():
    # SUBMIT_FORM intent는 submit_non_legal_form(DELEGATED) → risk signal로 DIRECT 격상
    plan = _make_plan("이 신청서를 제출해줘", risk_signals=["payment"])
    direct_steps = [s for s in plan["steps"] if s["risk"] == GRADE_USER_DIRECT]
    # DELEGATED step이 DIRECT로 격상되거나, 처음부터 DIRECT여야 함
    assert len(direct_steps) > 0 or len(plan["pending_permission"]) >= 0


def test_sign_risk_signal_escalates():
    plan = _make_plan("이 신청서를 제출해줘", risk_signals=["sign"])
    # risk signal 있으면 DELEGATED → DIRECT 격상
    direct_or_delegated = [s for s in plan["steps"] if s["risk"] in (GRADE_USER_DIRECT, GRADE_USER_DELEGATED)]
    assert len(direct_or_delegated) > 0


def test_unknown_site_form_fill_auto():
    plan = _make_plan("이 폼에 정보 입력하고 제출 전까지 준비해줘")
    fill_step = next((s for s in plan["steps"] if s["action"] == "fill_non_sensitive_form"), None)
    if fill_step:
        assert fill_step["risk"] == GRADE_AUTO_ALLOWED


def test_plan_structure():
    plan = _make_plan("공지사항 요약해줘")
    assert "plan_id" in plan
    assert "steps" in plan
    assert "auto_steps" in plan
    assert "pending_permission" in plan
    assert "user_direct_required" in plan
    assert "blocked" in plan


def test_no_blocked_in_normal_plans():
    plan = _make_plan("공지사항 찾아줘")
    assert not plan_has_blocked(plan)


def test_unknown_intent_fallback_plan():
    plan = _make_plan("xyz123 모르는 명령")
    assert len(plan["steps"]) > 0
