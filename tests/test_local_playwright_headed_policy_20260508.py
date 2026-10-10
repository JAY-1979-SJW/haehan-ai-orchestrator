"""Playwright headed/headless 정책 테스트

get_launch_options()의 정책 분기와 BROWSER_POLICY 상수를 검증한다.
실제 브라우저를 실행하지 않는다.
"""

from __future__ import annotations

from core.agent_runtime.runtime.playwright.playwright_bootstrap import (
    BROWSER_POLICY,
    get_launch_options,
)

# ── 1. 기본(headless) 경로 ────────────────────────────────────────────────────


def test_default_headless_true():
    opts = get_launch_options()
    assert opts["headless"] is True


def test_default_bring_to_front_false():
    opts = get_launch_options()
    assert opts["bring_to_front"] is False


def test_default_reason_present():
    opts = get_launch_options()
    assert "reason" in opts
    assert opts["reason"]


def test_default_no_sensitive_keys():
    opts = get_launch_options()
    for key in ("password", "cookie", "session", "otp"):
        assert key not in opts


# ── 2. 인증 필요(headed) 경로 ─────────────────────────────────────────────────


def test_auth_required_headless_false():
    opts = get_launch_options(requires_user_auth=True)
    assert opts["headless"] is False


def test_auth_required_bring_to_front_true():
    opts = get_launch_options(requires_user_auth=True)
    assert opts["bring_to_front"] is True


def test_auth_required_reason_present():
    opts = get_launch_options(requires_user_auth=True)
    assert "reason" in opts
    assert opts["reason"]


def test_auth_required_reason_mentions_auth():
    opts = get_launch_options(requires_user_auth=True)
    reason = opts["reason"]
    assert "인증" in reason or "auth" in reason.lower()


def test_auth_headed_no_sensitive_keys():
    opts = get_launch_options(requires_user_auth=True)
    for key in ("password", "cookie", "session", "otp"):
        assert key not in opts


# ── 3. 정책 분기 일관성 ───────────────────────────────────────────────────────


def test_headless_and_auth_are_mutually_exclusive():
    """headed 모드와 headless 모드는 동시에 True가 되면 안 된다."""
    headless_opts = get_launch_options(requires_user_auth=False)
    headed_opts = get_launch_options(requires_user_auth=True)
    # 한쪽이 True이면 다른 쪽은 False
    assert headless_opts["headless"] != headed_opts["headless"]


def test_bring_to_front_only_when_headed():
    headless_opts = get_launch_options(requires_user_auth=False)
    headed_opts = get_launch_options(requires_user_auth=True)
    assert headless_opts["bring_to_front"] is False
    assert headed_opts["bring_to_front"] is True


# ── 4. BROWSER_POLICY와 일관성 ────────────────────────────────────────────────


def test_launch_options_default_matches_policy():
    """get_launch_options()의 headless 기본값은 BROWSER_POLICY와 일치해야 한다."""
    opts = get_launch_options(requires_user_auth=False)
    assert opts["headless"] == BROWSER_POLICY["headless_default"]


def test_launch_options_auth_headed_matches_policy():
    opts = get_launch_options(requires_user_auth=True)
    # headed_on_user_auth_required=True이면 headless=False
    if BROWSER_POLICY["headed_on_user_auth_required"]:
        assert opts["headless"] is False


def test_launch_options_bring_to_front_matches_policy():
    opts = get_launch_options(requires_user_auth=True)
    assert opts["bring_to_front"] == BROWSER_POLICY["bring_to_front_on_auth_required"]


# ── 5. 정책 상수 불변성 ───────────────────────────────────────────────────────


def test_browser_policy_immutable_on_multiple_calls():
    """get_launch_options() 호출이 BROWSER_POLICY를 변경하면 안 된다."""
    original = dict(BROWSER_POLICY)
    get_launch_options(requires_user_auth=False)
    get_launch_options(requires_user_auth=True)
    assert dict(BROWSER_POLICY) == original


def test_get_launch_options_returns_new_dict():
    """호출마다 새 dict를 반환해야 한다."""
    opts1 = get_launch_options()
    opts2 = get_launch_options()
    assert opts1 is not opts2


def test_modifying_returned_opts_does_not_affect_policy():
    opts = get_launch_options(requires_user_auth=False)
    opts["headless"] = False  # 변조
    # BROWSER_POLICY는 영향 없어야 한다
    assert BROWSER_POLICY["headless_default"] is True
    # 재호출 시 원래 값 복원
    fresh = get_launch_options(requires_user_auth=False)
    assert fresh["headless"] is True
