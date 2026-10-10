"""tests/test_site_capability_matrix_20260508.py - site_capability_matrix 단위 테스트"""

from core.agent_runtime.runtime.site_profile.site_capability_matrix import (
    _CAPABILITY_GRADE,
    CAP_BID_DIRECT_ONLY,
    CAP_PAYMENT_DIRECT_ONLY,
    CAP_PUBLISH_WITH_PERMISSION,
    CAP_READONLY_EXPLORE,
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
    capability_allowed,
    get_capability_for_action,
    get_required_permission,
    get_required_risk_level,
    reject_if_blocked,
)
from core.agent_runtime.runtime.site_profile.site_profile_registry import get_site_profile


def test_readonly_explore_in_capability_grade():
    assert _CAPABILITY_GRADE.get(CAP_READONLY_EXPLORE) == GRADE_AUTO_ALLOWED


def test_publish_requires_delegated():
    assert _CAPABILITY_GRADE.get(CAP_PUBLISH_WITH_PERMISSION) == GRADE_USER_DELEGATED


def test_payment_requires_direct():
    assert _CAPABILITY_GRADE.get(CAP_PAYMENT_DIRECT_ONLY) == GRADE_USER_DIRECT


def test_bid_requires_direct():
    assert _CAPABILITY_GRADE.get(CAP_BID_DIRECT_ONLY) == GRADE_USER_DIRECT


def test_capability_allowed_naver_blog():
    # naver_blog는 READONLY_EXPLORE를 지원해야 함
    assert capability_allowed("naver_blog", CAP_READONLY_EXPLORE) is True


def test_capability_allowed_unknown_site():
    assert capability_allowed("unknown_site_xyz", CAP_READONLY_EXPLORE) is False


def test_get_required_risk_level_blog_publish():
    # CAP_PUBLISH_WITH_PERMISSION의 grade를 직접 조회
    level = get_required_risk_level("naver_blog", CAP_PUBLISH_WITH_PERMISSION)
    assert level == GRADE_USER_DELEGATED


def test_get_required_risk_level_search():
    from core.agent_runtime.runtime.site_profile.site_capability_matrix import CAP_SEARCH

    level = get_required_risk_level("naver", CAP_SEARCH)
    assert level == GRADE_AUTO_ALLOWED


def test_get_capability_for_action_known():
    cap = get_capability_for_action("cafe_post_write")
    assert cap is not None


def test_get_capability_for_action_unknown():
    cap = get_capability_for_action("completely_unknown_action_xyz")
    assert cap is None


def test_get_required_permission_delegated():
    result = get_required_permission("naver_blog", "blog_publish")
    assert result["grade"] == GRADE_USER_DELEGATED
    assert result["requires_permission"] is True


def test_get_required_permission_blocked():
    result = get_required_permission("naver_blog", "password_save")
    assert result["grade"] == GRADE_BLOCKED


def test_reject_if_blocked_auto_does_not_raise():
    reject_if_blocked("naver_blog", "readonly_explore")  # 예외 없어야 함


def test_reject_if_blocked_returns_blocked_dict():
    result = reject_if_blocked("naver_blog", "password_save")
    assert result is not None
    assert result.get("blocked") is True


def test_site_capabilities_consistency():
    """naver_blog가 지원하는 capabilities는 모두 matrix에 존재해야 함"""
    profile = get_site_profile("naver_blog")
    for cap in profile.get("supported_capabilities", []):
        assert cap in _CAPABILITY_GRADE, f"capability {cap}이 matrix에 없음"
