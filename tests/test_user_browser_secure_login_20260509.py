"""user_browser_secure_login 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_orchestrator.local_agent.browser.secure_login import (
    EASY_AUTH_KAKAO,
    LOGIN_CERT,
    LOGIN_OK,
    LOGIN_REQUIRED,
    LOGIN_TWO_FACTOR,
    SITE_LOGIN_CONFIG,
    detect_login_state,
    ensure_logged_in,
    input_credential,
    is_cert_required,
    is_logged_in,
    is_two_factor_required,
    try_easy_auth,
)


def _make_page(text: str = "", url: str = "https://www.gov.kr/"):
    page = MagicMock()
    page.url = url
    page.inner_text.return_value = text
    return page


# ── detect_login_state ────────────────────────────────────────────────────────


def test_detect_logged_in_gov24():
    page = _make_page("마이페이지 | 로그아웃", url="https://www.gov.kr/")
    assert detect_login_state(page, "www.gov.kr") == LOGIN_OK


def test_detect_login_required_gov24():
    page = _make_page("로그인 | 간편인증", url="https://www.gov.kr/")
    assert detect_login_state(page, "www.gov.kr") == LOGIN_REQUIRED


def test_detect_two_factor_gov24():
    page = _make_page("OTP 인증 코드를 입력하세요", url="https://www.gov.kr/")
    assert detect_login_state(page, "www.gov.kr") == LOGIN_TWO_FACTOR


def test_detect_cert_required():
    page = _make_page("공동인증서를 선택하세요", url="https://www.gov.kr/")
    assert detect_login_state(page, "www.gov.kr") == LOGIN_CERT


def test_is_logged_in_true():
    page = _make_page("로그아웃 | 내 신청내역", url="https://www.gov.kr/")
    assert is_logged_in(page, "www.gov.kr") is True


def test_is_logged_in_false():
    page = _make_page("로그인이 필요합니다", url="https://www.gov.kr/")
    assert is_logged_in(page, "www.gov.kr") is False


def test_is_two_factor_required():
    page = _make_page("2차 인증 필요: OTP", url="https://www.gov.kr/")
    assert is_two_factor_required(page, "www.gov.kr") is True


def test_is_cert_required():
    page = _make_page("공인인증서를 선택", url="https://www.gov.kr/")
    assert is_cert_required(page, "www.gov.kr") is True


def test_detect_epeople_logged_in():
    page = _make_page("내 민원 | 로그아웃", url="https://www.epeople.go.kr/")
    assert detect_login_state(page, "www.epeople.go.kr") == LOGIN_OK


def test_detect_gmail_two_factor():
    page = _make_page("2단계 인증 코드 입력", url="https://mail.google.com/")
    assert detect_login_state(page, "mail.google.com") == LOGIN_TWO_FACTOR


# ── SITE_LOGIN_CONFIG ─────────────────────────────────────────────────────────


def test_all_sites_have_required_keys():
    required = {"name", "login_indicators", "logged_in_indicators", "easy_auth"}
    for site, cfg in SITE_LOGIN_CONFIG.items():
        missing = required - set(cfg.keys())
        assert not missing, f"{site} 설정 누락: {missing}"


def test_gov24_has_kakao_easy_auth():
    cfg = SITE_LOGIN_CONFIG["www.gov.kr"]
    assert EASY_AUTH_KAKAO in cfg["easy_auth"]


def test_gov24_has_cert_btn():
    cfg = SITE_LOGIN_CONFIG["www.gov.kr"]
    assert cfg.get("cert_btn") is not None


def test_epeople_has_easy_auth():
    cfg = SITE_LOGIN_CONFIG["www.epeople.go.kr"]
    assert len(cfg["easy_auth"]) > 0


# ── try_easy_auth (mock) ──────────────────────────────────────────────────────


def test_try_easy_auth_no_selector_returns_required():
    page = _make_page(url="https://www.gov.kr/")
    # 지원하지 않는 method
    result = try_easy_auth(page, method="unknown_method", site_host="www.gov.kr")
    assert result.status == LOGIN_REQUIRED
    assert result.method_used == "unknown_method"


def test_try_easy_auth_click_fail_returns_required():
    page = _make_page(url="https://www.gov.kr/")
    page.click.side_effect = Exception("element not found")

    with patch("ai_orchestrator.local_agent.browser.secure_login.click") as mock_click:
        from ai_orchestrator.local_agent.browser.actions import ActionResult

        mock_click.return_value = ActionResult("click", ok=False, error="not found")

        result = try_easy_auth(page, EASY_AUTH_KAKAO, site_host="www.gov.kr")
        assert result.status == LOGIN_REQUIRED


def test_try_easy_auth_success_detected(tmp_path):
    page = _make_page(text="마이페이지 | 로그아웃", url="https://www.gov.kr/")

    with (
        patch("ai_orchestrator.local_agent.browser.secure_login.click") as mock_click,
        patch("ai_orchestrator.local_agent.browser.secure_login.time.sleep"),
        patch("ai_orchestrator.local_agent.browser.secure_login.time.time") as mock_time,
    ):
        from ai_orchestrator.local_agent.browser.actions import ActionResult

        mock_click.return_value = ActionResult("click", ok=True)
        mock_time.side_effect = [0, 1]  # 첫 호출=시작, 폴링=1초

        result = try_easy_auth(
            page, EASY_AUTH_KAKAO, site_host="www.gov.kr", audit_path=tmp_path / "log.jsonl", wait_seconds=60
        )
        assert result.status == LOGIN_OK


# ── ensure_logged_in (이미 로그인) ────────────────────────────────────────────


def test_ensure_logged_in_already_logged_in():
    page = _make_page(text="로그아웃 | 마이페이지", url="https://www.gov.kr/")
    result = ensure_logged_in(page, site_host="www.gov.kr")
    assert result.ok is True
    assert result.method_used == "session"


def test_ensure_logged_in_result_has_site():
    page = _make_page(text="로그아웃", url="https://www.gov.kr/")
    result = ensure_logged_in(page, site_host="www.gov.kr")
    assert result.site == "www.gov.kr"


# ── LoginResult ───────────────────────────────────────────────────────────────


def test_login_result_ok_property():
    from ai_orchestrator.local_agent.browser.secure_login import LoginResult

    r = LoginResult(status=LOGIN_OK)
    assert r.ok is True


def test_login_result_not_ok():
    from ai_orchestrator.local_agent.browser.secure_login import LoginResult

    r = LoginResult(status=LOGIN_REQUIRED)
    assert r.ok is False


# ── input_credential ─────────────────────────────────────────────────────────


def test_input_credential_approved(tmp_path):
    page = _make_page(url="https://www.gov.kr/")
    # request_approval은 Flask 서버를 기동하므로 반드시 mock해야 함
    with (
        patch("ai_orchestrator.local_agent.browser.secure_login.request_approval", return_value=True),
        patch("ai_orchestrator.local_agent.browser.secure_login.type_text") as mock_type,
    ):
        from ai_orchestrator.local_agent.browser.actions import ActionResult

        mock_type.return_value = ActionResult("type", ok=True)
        result = input_credential(
            page, "input[name='password']", "s3cret", field_label="비밀번호", audit_path=tmp_path / "log.jsonl"
        )
        assert result is True
        mock_type.assert_called_once()


def test_input_credential_rejected(tmp_path):
    page = _make_page(url="https://www.gov.kr/")
    with patch("ai_orchestrator.local_agent.browser.secure_login.request_approval", return_value=False):
        result = input_credential(
            page, "input[name='password']", "s3cret", field_label="비밀번호", audit_path=tmp_path / "log.jsonl"
        )
        assert result is False


def test_input_credential_otp(tmp_path):
    page = _make_page(url="https://www.gov.kr/")
    # request_approval은 Flask 서버를 기동하므로 반드시 mock해야 함
    with (
        patch("ai_orchestrator.local_agent.browser.secure_login.request_approval", return_value=True),
        patch("ai_orchestrator.local_agent.browser.secure_login.type_text") as mock_type,
    ):
        from ai_orchestrator.local_agent.browser.actions import ActionResult

        mock_type.return_value = ActionResult("type", ok=True)
        result = input_credential(page, "input#otp", "123456", field_label="OTP", audit_path=tmp_path / "log.jsonl")
        assert result is True


# ── minwon_submit 승인 정책 확인 ──────────────────────────────────────────────


def test_minwon_submit_no_early_approval():
    """minwon_submit.py는 폼 작성 이전이 아닌 제출 직전에만 승인을 요청해야 한다.

    canonical 경로: scripts/local_agent/gov/minwon_submit.py
    (구 경로 scripts/local_agent/minwon_submit.py에서 gov/ 하위로 이전됨)
    """
    import pathlib

    src = pathlib.Path("scripts/local_agent/gov/minwon_submit.py").read_text(encoding="utf-8")
    lines = src.splitlines()

    # 함수 정의(def)가 아닌 호출 위치만 찾기
    approval_calls = [
        i
        for i, l in enumerate(lines)  # noqa: E741
        if "_ask_submit_approval(" in l and not l.strip().startswith("def ")
    ]
    fill_calls = [
        i
        for i, l in enumerate(lines)  # noqa: E741
        if "_fill_epeople_form(" in l and not l.strip().startswith("def ")
    ]
    assert approval_calls, "_ask_submit_approval 호출이 없음"
    assert fill_calls, "_fill_epeople_form 호출이 없음"
    # 제출 승인 호출이 폼 작성 호출보다 뒤에 있어야 함
    assert min(approval_calls) > min(fill_calls), "제출 승인이 폼 작성 이전에 위치함"
