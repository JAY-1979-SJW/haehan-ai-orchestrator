"""ORCHESTRATOR_MAIN_PAGE_FIRST_ENTRY_POLICY_01 — site_entry_policy 단위 테스트."""
from __future__ import annotations

import pytest

from core.agent_runtime.policy import site_entry_policy as sep

# ── 1) 정책 lookup ───────────────────────────────────────────────────


def test_l1_naver_policy_registered():
    p = sep.get("naver")
    assert p is not None
    assert p.main_url == "https://www.naver.com/"
    assert p.forbid_login_url_direct is True


def test_l1_all_required_sites_registered():
    for k in ("naver", "naver_blog", "naver_cafe", "google", "youtube",
              "kakao", "daum", "eum"):
        assert sep.get(k) is not None, f"{k} 미등록"


def test_l1_main_urls_never_login_only():
    """모든 등록 정책의 main_url 은 로그인 전용 URL 이 아니어야 한다."""
    for p in sep.all_policies():
        assert not sep.is_login_url_forbidden(p.main_url), (
            f"{p.site_key} main_url 이 로그인 전용 URL: {p.main_url}"
        )


# ── 2) 로그인 URL 직접 진입 금지 ────────────────────────────────────


@pytest.mark.parametrize("url", [
    "https://nid.naver.com/nidlogin.login",
    "https://nid.naver.com/nidlogin.login?mode=form",
    "https://accounts.google.com/",
    "https://accounts.google.com/ServiceLogin",
    "https://accounts.kakao.com/login",
    "https://logins.daum.net/accounts/loginform.do",
    "https://www.youtube.com/signin",
])
def test_l2_forbidden_login_urls_detected(url):
    assert sep.is_login_url_forbidden(url) is True


@pytest.mark.parametrize("url", [
    "https://www.naver.com/",
    "https://section.blog.naver.com/BlogHome.naver",
    "https://section.cafe.naver.com/",
    "https://www.google.com/",
    "https://www.youtube.com/",
    "https://www.daum.net/",
    "https://eum.cw.or.kr/",
])
def test_l2_main_urls_not_forbidden(url):
    assert sep.is_login_url_forbidden(url) is False


def test_l2_assert_main_page_first_raises_on_nidlogin():
    with pytest.raises(ValueError, match="FORBIDDEN_LOGIN_URL_DIRECT_ENTRY"):
        sep.assert_main_page_first(
            "https://nid.naver.com/nidlogin.login", site_key="naver",
        )


def test_l2_assert_main_page_first_passes_on_main():
    # 예외 없음
    sep.assert_main_page_first("https://www.naver.com/", site_key="naver")


# ── 3) resolve_entry: main 먼저 → work url ──────────────────────────


def test_l3_resolve_entry_returns_main_first():
    first, follow = sep.resolve_entry(
        "naver_blog",
        work_url="https://blog.naver.com/PostWriteForm.naver",
    )
    assert first == "https://section.blog.naver.com/BlogHome.naver"
    assert follow == "https://blog.naver.com/PostWriteForm.naver"


def test_l3_resolve_entry_default_work_url():
    first, follow = sep.resolve_entry("naver")
    assert first == "https://www.naver.com/"
    assert follow == "https://www.naver.com/"


def test_l3_resolve_entry_unknown_site_passthrough():
    first, follow = sep.resolve_entry("unknown", work_url="https://x/y")
    assert first == "https://x/y"
    assert follow == "https://x/y"


# ── 4) judge_login_state ────────────────────────────────────────────


def test_l4_logged_in_when_has_logout():
    s = sep.judge_login_state("naver", {
        "has_logout": True,
        "has_id_form": False,
        "has_pw_form": False,
    })
    assert s == sep.STATE_LOGGED_IN


def test_l4_logged_in_when_mypage_link():
    s = sep.judge_login_state("naver", {
        "has_mypage_link": True,
    })
    assert s == sep.STATE_LOGGED_IN


def test_l4_login_required_on_id_pw_form_without_cookie():
    s = sep.judge_login_state("naver", {
        "has_id_form": True,
        "has_pw_form": True,
    })
    assert s == sep.STATE_LOGIN_REQUIRED


def test_l4_session_expired_when_form_plus_cookie():
    s = sep.judge_login_state("naver", {
        "has_id_form": True,
        "has_pw_form": True,
        "has_naver_session_cookie": True,
    })
    assert s == sep.STATE_SESSION_EXPIRED


def test_l4_session_expired_on_relogin_msg():
    s = sep.judge_login_state("naver", {
        "has_relogin_msg": True,
    })
    assert s == sep.STATE_SESSION_EXPIRED


def test_l4_unknown_when_no_signal():
    s = sep.judge_login_state("naver", {})
    assert s == sep.STATE_LOGIN_UNKNOWN


# ── 5) blog/cafe write 진입로 — 메인 우선 정책 통과 ────────────────


def test_l5_blog_write_routed_via_main_first():
    """blog_write 가 PostWriteForm 으로 곧장 갈 때도 main_url 을 1차 진입으로 받아야."""
    first, follow = sep.resolve_entry(
        "naver_blog",
        work_url="https://blog.naver.com/PostWriteForm.naver",
    )
    # 1차 진입은 메인, follow-up 만 실제 work
    assert first.startswith("https://section.blog.naver.com/")
    assert "PostWriteForm" in follow


def test_l5_cafe_write_routed_via_main_first():
    first, follow = sep.resolve_entry(
        "naver_cafe",
        work_url="https://cafe.naver.com/MyCafeIntro.nhn",
    )
    assert first.startswith("https://section.cafe.naver.com/")
    assert "cafe.naver.com" in follow
