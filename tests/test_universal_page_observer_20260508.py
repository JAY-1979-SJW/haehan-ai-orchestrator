"""tests/test_universal_page_observer_20260508.py"""

from core.agent_runtime.runtime.universal.universal_page_observer import (
    observe_page_from_dict,
    observe_page_mock,
)

_SAFE_MARKER_FIELDS = [
    "password_value_read",
    "otp_value_read",
    "cookie_read",
    "session_read",
    "storage_state_read",
    "server_browser_used",
]


def test_observe_returns_host():
    obs = observe_page_mock(url="https://notice.example.com/list", title="공지사항")
    assert obs["host"] == "notice.example.com"


def test_observe_safe_fields_always_false():
    obs = observe_page_mock(url="https://any.site.com", title="test")
    for f in _SAFE_MARKER_FIELDS:
        assert obs[f] is False, f"{f} != False"


def test_password_value_never_read():
    obs = observe_page_mock(
        url="https://login.example.com",
        text="로그인 페이지",
        form_labels=["아이디", "비밀번호"],
    )
    assert obs["password_value_read"] is False


def test_otp_value_never_read():
    obs = observe_page_mock(
        url="https://auth.example.com",
        text="OTP 입력",
        form_labels=["OTP", "인증번호"],
    )
    assert obs["otp_value_read"] is False


def test_cookie_never_read():
    obs = observe_page_mock(url="https://any.com", text="cookie session")
    assert obs["cookie_read"] is False
    assert obs["session_read"] is False


def test_storage_state_never_read():
    obs = observe_page_mock(url="https://any.com", text="storage_state token")
    assert obs["storage_state_read"] is False


def test_page_type_candidates_notice():
    obs = observe_page_mock(
        url="https://notice.example.com",
        title="공지사항 목록",
        text="공지 | 알림 | 목록",
    )
    assert "notice_board" in obs["page_type_candidates"]


def test_page_type_candidates_blog():
    obs = observe_page_mock(
        url="https://blog.example.com",
        title="블로그",
        text="블로그 포스팅 새글",
    )
    assert "blog" in obs["page_type_candidates"]


def test_visible_actions_search():
    obs = observe_page_mock(
        url="https://any.com",
        buttons=["검색", "목록보기"],
    )
    assert "search" in obs["visible_actions"]


def test_visible_actions_download():
    obs = observe_page_mock(
        url="https://any.com",
        links=["report.pdf", "data.xlsx"],
        buttons=["다운로드"],
    )
    assert "download" in obs["visible_actions"]


def test_auth_signals_detected():
    obs = observe_page_mock(
        url="https://any.com",
        text="로그인이 필요합니다. 로그아웃",
    )
    assert len(obs["auth_signals"]) > 0


def test_risk_signals_detected():
    obs = observe_page_mock(
        url="https://any.com",
        text="결제 | 카드 | 계좌이체",
    )
    assert "payment" in obs["risk_signals"]


def test_download_candidates_from_links():
    obs = observe_page_mock(
        url="https://any.com",
        links=["notice.pdf", "excel.xlsx", "대한민국.hwp"],
    )
    assert len(obs["download_candidates"]) >= 2


def test_forms_detected():
    obs = observe_page_from_dict(
        {
            "url": "https://apply.com",
            "title": "신청",
            "text_content": "",
            "buttons": ["제출"],
            "links": [],
            "form_labels": ["이름", "연락처"],
            "has_file_inputs": False,
            "heading_texts": [],
        }
    )
    assert obs["forms_detected"] is True


def test_server_browser_used_always_false():
    obs = observe_page_mock(url="https://any.com")
    assert obs["server_browser_used"] is False
