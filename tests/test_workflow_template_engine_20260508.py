"""tests/test_workflow_template_engine_20260508.py - workflow_template_engine 단위 테스트"""

import pytest

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
)
from core.agent_runtime.runtime.universal.workflow_template_engine import (
    get_auto_steps,
    get_delegated_steps,
    get_template,
    is_template_registered,
    register_template,
)

_EXPECTED_TEMPLATES = [
    "readonly_site_explore",
    "download_documents",
    "content_research_summary",
    "cafe_to_blog_draft",
    "blog_publish_with_permission",
    "comment_with_permission",
    "generic_form_fill_preview",
    "government_readonly_status_check",
    "financial_readonly_statement_download",
    "ecommerce_order_status_readonly",
]


def test_all_templates_registered():
    for tid in _EXPECTED_TEMPLATES:
        assert is_template_registered(tid), f"템플릿 미등록: {tid}"


def test_get_template_returns_dict():
    tmpl = get_template("readonly_site_explore")
    assert isinstance(tmpl, dict)
    assert "steps" in tmpl


def test_template_step_structure():
    for tid in _EXPECTED_TEMPLATES:
        tmpl = get_template(tid)
        for step in tmpl["steps"]:
            assert "step_id" in step or "action" in step, f"{tid}: 스텝에 step_id/action 누락"
            assert "risk_level" in step, f"{tid}: risk_level 누락"


def test_readonly_template_no_delegated_steps():
    auto = get_auto_steps("readonly_site_explore")
    delegated = get_delegated_steps("readonly_site_explore")
    assert len(auto) > 0
    assert len(delegated) == 0


def test_blog_publish_template_has_delegated_step():
    delegated = get_delegated_steps("blog_publish_with_permission")
    assert len(delegated) > 0


def test_government_readonly_all_auto():
    auto = get_auto_steps("government_readonly_status_check")
    delegated = get_delegated_steps("government_readonly_status_check")
    assert len(auto) > 0
    assert len(delegated) == 0


def test_get_template_unknown_returns_none():
    tmpl = get_template("nonexistent_template_xyz")
    assert tmpl is None


def test_register_custom_template():
    custom_tmpl = {
        "workflow_id": "test_custom_template_engine",
        "display_name": "테스트 커스텀 템플릿",
        "steps": [
            {
                "step_id": "s1",
                "action": "readonly_explore",
                "risk_level": GRADE_AUTO_ALLOWED,
                "optional": False,
                "description": "탐색",
            },
        ],
    }
    register_template(custom_tmpl)
    assert is_template_registered("test_custom_template_engine")


def test_register_no_steps_raises():
    with pytest.raises(ValueError):
        register_template({"workflow_id": "test_no_steps_tmpl", "steps": []})


def test_blocked_step_not_in_templates():
    """어떤 템플릿에도 BLOCKED 스텝이 없어야 함"""
    for tid in _EXPECTED_TEMPLATES:
        tmpl = get_template(tid)
        for step in tmpl["steps"]:
            assert step["risk_level"] != GRADE_BLOCKED, f"{tid}: BLOCKED 스텝 포함"
