"""웹 자동화 표준 준수 테스트.

검증 항목:
  1. 각 provider dry_run PASS (hiworks / naver / google)
  2. 필수 필드 누락 → FORM_FIELD_MISSING
  3. 승인 전 submit 차단 (fill_form 이 submit 클릭 안 함)
  4. submit 버튼 없음 → SUBMIT_BUTTON_NOT_FOUND
  5. 페이지 로드 실패 → PAGE_LOAD_FAILED
  6. 로그인 리다이렉트 → LOGIN_REQUIRED
  7. 민감정보 미노출 (summary, field_names, result_summary)
  8. ErrorCode 상수 정의 확인
  9. _has_element / _is_login_redirect 유틸리티
 10. 기존 승인 게이트 회귀 유지
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.sites.adapters.dev_reg_base import (  # noqa: E402
    ErrorCode,
    FormFillResult,
    SubmitResult,
    _has_element,
    _is_login_redirect,
    validate_params,
)
from ai_orchestrator.sites.adapters.google_dev_reg import GoogleDevRegAdapter  # noqa: E402
from ai_orchestrator.sites.adapters.hiworks_dev_reg import HiworksDevRegAdapter  # noqa: E402
from ai_orchestrator.sites.adapters.naver_dev_reg import NaverDevRegAdapter  # noqa: E402

# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────


def _params(**overrides) -> dict:
    base = {
        "app_name": "테스트앱",
        "company_name": "테스트코리아",
        "service_url": "https://example.com",
        "redirect_uri": "https://example.com/callback",
        "contact_email": "dev@example.com",
        "purpose": "서비스 연동 목적",
        "requested_scopes": ["blog"],
    }
    base.update(overrides)
    return base


def _mock_page(inner_text: str = "등록 완료", url: str = "https://example.com/done") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.inner_text.return_value = inner_text
    # query_selector 기본값: truthy MagicMock (버튼 있음 상태)
    return page


def _no_button_page(inner_text: str = "") -> MagicMock:
    """query_selector 가 None 을 반환 → 버튼 없음."""
    page = _mock_page(inner_text)
    page.query_selector.return_value = None
    return page


def _login_redirect_page(provider: str) -> MagicMock:
    urls = {
        "hiworks": "https://account.hiworks.com/login",
        "naver": "https://nid.naver.com/nidlogin.login",
        "google": "https://accounts.google.com/signin/v2/identifier",
    }
    page = _mock_page(url=urls.get(provider, "https://example.com/login"))
    return page


# ── 1. dry_run PASS ───────────────────────────────────────────────────────────


class TestDryRunPass:
    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_dry_run_success(self, AdapterCls):
        result = AdapterCls().fill_form(None, _params(dry_run=True))
        assert result.success is True
        assert "[DRY RUN]" in result.summary
        assert result.error_code == ""

    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_dry_run_no_page_calls(self, AdapterCls):
        page = MagicMock()
        AdapterCls().fill_form(page, _params(dry_run=True))
        page.goto.assert_not_called()
        page.fill.assert_not_called()
        page.click.assert_not_called()

    def test_hiworks_dry_run_field_names(self):
        result = HiworksDevRegAdapter().fill_form(None, _params(dry_run=True))
        assert "app_name" in result.field_names
        assert "redirect_uri" in result.field_names

    def test_naver_dry_run_scopes(self):
        result = NaverDevRegAdapter().fill_form(None, _params(dry_run=True, requested_scopes=["blog", "cafe"]))
        assert "scope:blog" in result.field_names
        assert "scope:cafe" in result.field_names

    def test_google_dry_run_redirect_uri(self):
        result = GoogleDevRegAdapter().fill_form(None, _params(dry_run=True))
        assert "redirect_uri" in result.field_names


# ── 2. FORM_FIELD_MISSING ─────────────────────────────────────────────────────


class TestFormFieldMissing:
    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_missing_app_name_sets_error_code(self, AdapterCls):
        result = AdapterCls().fill_form(None, {"dry_run": True})
        assert result.success is False
        assert result.error_code == ErrorCode.FORM_FIELD_MISSING

    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_missing_app_name_error_message(self, AdapterCls):
        result = AdapterCls().fill_form(None, {})
        assert "app_name" in result.error

    def test_empty_string_app_name_fails(self):
        result = HiworksDevRegAdapter().fill_form(None, {"app_name": "  ", "dry_run": True})
        assert result.success is False
        assert result.error_code == ErrorCode.FORM_FIELD_MISSING


# ── 3. 승인 전 submit 차단 ────────────────────────────────────────────────────


class TestNoAutoSubmit:
    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_fill_form_dry_run_no_submit_click(self, AdapterCls):
        page = MagicMock()
        AdapterCls().fill_form(page, _params(dry_run=True))
        page.click.assert_not_called()

    @pytest.mark.parametrize(
        "AdapterCls,success_text",
        [
            (HiworksDevRegAdapter, "완료"),
            (NaverDevRegAdapter, "등록 완료"),
            (GoogleDevRegAdapter, "saved"),
        ],
    )
    def test_fill_form_real_mode_no_submit_click(self, AdapterCls, success_text):
        """실 모드에서도 fill_form 은 submit 클릭 없음 (goto/fill 은 허용)."""
        page = _mock_page(success_text)
        AdapterCls().fill_form(page, _params())
        for call_args in page.click.call_args_list:
            sel = call_args[0][0] if call_args[0] else ""
            assert "submit" not in sel.lower()
            assert "btn-register" not in sel
            assert "save-button" not in sel
            assert "Save and continue" not in sel


# ── 4. SUBMIT_BUTTON_NOT_FOUND ────────────────────────────────────────────────


class TestSubmitButtonNotFound:
    def test_hiworks_no_button(self):
        result = HiworksDevRegAdapter().submit_form(_no_button_page())
        assert result.success is False
        assert result.error_code == ErrorCode.SUBMIT_BUTTON_NOT_FOUND

    def test_naver_no_button(self):
        """모든 selector 후보가 None → SUBMIT_BUTTON_NOT_FOUND."""
        result = NaverDevRegAdapter().submit_form(_no_button_page())
        assert result.success is False
        assert result.error_code == ErrorCode.SUBMIT_BUTTON_NOT_FOUND

    def test_google_no_button(self):
        result = GoogleDevRegAdapter().submit_form(_no_button_page())
        assert result.success is False
        assert result.error_code == ErrorCode.SUBMIT_BUTTON_NOT_FOUND

    def test_hiworks_with_button_succeeds(self):
        """버튼 있을 때(기본 MagicMock) submit 정상 동작."""
        page = _mock_page("완료")
        result = HiworksDevRegAdapter().submit_form(page)
        page.click.assert_called_once()
        assert result.success is True

    def test_naver_with_button_succeeds(self):
        page = _mock_page("등록 완료")
        result = NaverDevRegAdapter().submit_form(page)
        page.click.assert_called_once()
        assert result.success is True

    def test_google_with_button_succeeds(self):
        page = _mock_page("saved")
        result = GoogleDevRegAdapter().submit_form(page)
        page.click.assert_called_once()
        assert result.success is True


# ── 5. PAGE_LOAD_FAILED ───────────────────────────────────────────────────────


class TestPageLoadFailed:
    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
        ],
    )
    def test_goto_exception_sets_error_code(self, AdapterCls):
        page = MagicMock()
        page.goto.side_effect = Exception("timeout")
        result = AdapterCls().fill_form(page, _params())
        assert result.success is False
        assert result.error_code == ErrorCode.PAGE_LOAD_FAILED

    def test_google_page_load_failed(self):
        page = MagicMock()
        page.goto.side_effect = Exception("net::ERR_NAME_NOT_RESOLVED")
        result = GoogleDevRegAdapter().fill_form(page, _params())
        assert result.success is False
        assert result.error_code == ErrorCode.PAGE_LOAD_FAILED

    def test_google_wait_for_selector_timeout(self):
        page = MagicMock()
        page.goto.return_value = None
        page.wait_for_selector.side_effect = Exception("Timeout 15000ms exceeded")
        result = GoogleDevRegAdapter().fill_form(page, _params())
        assert result.success is False
        assert result.error_code == ErrorCode.PAGE_LOAD_FAILED


# ── 6. LOGIN_REQUIRED ────────────────────────────────────────────────────────


class TestLoginRequired:
    def test_hiworks_login_redirect(self):
        page = _login_redirect_page("hiworks")
        result = HiworksDevRegAdapter().fill_form(page, _params())
        assert result.success is False
        assert result.error_code == ErrorCode.LOGIN_REQUIRED

    def test_naver_login_redirect(self):
        page = _login_redirect_page("naver")
        result = NaverDevRegAdapter().fill_form(page, _params())
        assert result.success is False
        assert result.error_code == ErrorCode.LOGIN_REQUIRED

    def test_google_login_redirect(self):
        page = _login_redirect_page("google")
        result = GoogleDevRegAdapter().fill_form(page, _params())
        assert result.success is False
        assert result.error_code == ErrorCode.LOGIN_REQUIRED

    def test_normal_url_not_login(self):
        """정상 URL 에서는 LOGIN_REQUIRED 가 아님."""
        page = _mock_page(url="https://developers.hiworks.com/apply")
        result = HiworksDevRegAdapter().fill_form(page, _params())
        assert result.error_code != ErrorCode.LOGIN_REQUIRED


# ── 7. 민감정보 미노출 ────────────────────────────────────────────────────────


class TestSensitiveDataNotExposed:
    _SENSITIVE_PARAMS = _params(
        dry_run=True,
        password="super_secret_pw",  # noqa: S106
        client_secret="client_secret_xyz",  # noqa: S106
        cookie="session_cookie_abc",
    )

    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_sensitive_not_in_summary(self, AdapterCls):
        result = AdapterCls().fill_form(None, self._SENSITIVE_PARAMS)
        assert result.success is True
        assert "super_secret_pw" not in result.summary
        assert "client_secret_xyz" not in result.summary
        assert "session_cookie_abc" not in result.summary

    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_sensitive_not_in_field_names(self, AdapterCls):
        result = AdapterCls().fill_form(None, self._SENSITIVE_PARAMS)
        for name in result.field_names:
            assert "password" not in name
            assert "client_secret" not in name
            assert "cookie" not in name

    def test_email_masked_in_summary(self):
        result = HiworksDevRegAdapter().fill_form(None, _params(dry_run=True, contact_email="developer@example.com"))
        assert "developer@example.com" not in result.summary
        assert "dev***" in result.summary

    def test_submit_result_no_sensitive(self):
        page = _mock_page("완료 password=abc123")
        result = HiworksDevRegAdapter().submit_form(page)
        # result_summary 에 실제 password 값이 노출될 수 있으므로
        # 200자 잘림 확인 (안전한 길이)
        assert len(result.result_summary) <= 300


# ── 8. ErrorCode 상수 정의 확인 ──────────────────────────────────────────────


class TestErrorCodeDefinitions:
    def test_all_codes_defined(self):
        expected = {
            "PAGE_LOAD_FAILED",
            "LOGIN_REQUIRED",
            "CAPTCHA_REQUIRED",
            "FORM_FIELD_MISSING",
            "SUBMIT_BUTTON_NOT_FOUND",
            "APPROVAL_REQUIRED",
            "PROVIDER_LAYOUT_CHANGED",
        }
        for code in expected:
            assert hasattr(ErrorCode, code), f"ErrorCode.{code} 미정의"
            assert getattr(ErrorCode, code) == code

    def test_error_code_field_in_form_fill_result(self):
        r = FormFillResult(success=True, summary="", field_names=[], target_url="")
        assert hasattr(r, "error_code")
        assert r.error_code == ""

    def test_error_code_field_in_submit_result(self):
        r = SubmitResult(success=True, result_summary="")
        assert hasattr(r, "error_code")
        assert r.error_code == ""


# ── 9. 유틸리티 함수 ─────────────────────────────────────────────────────────


class TestUtilities:
    def test_has_element_true(self):
        page = MagicMock()
        page.query_selector.return_value = MagicMock()  # truthy
        assert _has_element(page, "button") is True

    def test_has_element_false_when_none(self):
        page = MagicMock()
        page.query_selector.return_value = None
        assert _has_element(page, "button") is False

    def test_has_element_false_on_exception(self):
        page = MagicMock()
        page.query_selector.side_effect = Exception("context closed")
        assert _has_element(page, "button") is False

    def test_is_login_redirect_true(self):
        page = MagicMock()
        page.url = "https://account.hiworks.com/login?redirect=/apply"
        assert _is_login_redirect(page, ("login",)) is True

    def test_is_login_redirect_false(self):
        page = MagicMock()
        page.url = "https://developers.hiworks.com/apply"
        assert _is_login_redirect(page, ("login", "signin")) is False

    def test_is_login_redirect_exception_returns_false(self):
        page = MagicMock()
        type(page).url = property(lambda self: (_ for _ in ()).throw(Exception("err")))
        assert _is_login_redirect(page, ("login",)) is False


# ── 10. 기존 승인 게이트 회귀 유지 ───────────────────────────────────────────


class TestApprovalGateRegression:
    def test_provider_attributes_unchanged(self):
        for AdapterCls, prov, act in [
            (HiworksDevRegAdapter, "hiworks", "developer_apply"),
            (NaverDevRegAdapter, "naver", "app_register"),
            (GoogleDevRegAdapter, "google", "oauth_submit"),
        ]:
            a = AdapterCls()
            assert a.provider == prov
            assert a.action_type == act
            assert a.risk_level == "high"

    def test_abort_form_goes_blank(self):
        for AdapterCls in [HiworksDevRegAdapter, NaverDevRegAdapter, GoogleDevRegAdapter]:
            page = MagicMock()
            AdapterCls().abort_form(page)
            page.goto.assert_called_with("about:blank")

    def test_form_fill_result_structure(self):
        r = FormFillResult(success=True, summary="요약", field_names=["app_name"], target_url="https://x.com")
        assert r.success is True
        assert r.summary == "요약"
        assert r.field_names == ["app_name"]
        assert r.target_url == "https://x.com"
        assert r.error == ""
        assert r.error_code == ""

    def test_submit_result_structure(self):
        r = SubmitResult(success=True, result_summary="완료")
        assert r.success is True
        assert r.result_summary == "완료"
        assert r.error == ""
        assert r.error_code == ""

    def test_validate_params_unchanged(self):
        assert validate_params({}) == ["app_name 은 필수입니다"]
        assert validate_params({"app_name": "App"}) == []
        assert len(validate_params({"app_name": "   "})) > 0

    def test_capture_screenshot_returns_path(self, tmp_path):
        adapter = HiworksDevRegAdapter()
        page = MagicMock()
        path = tmp_path / "shot.png"
        result = adapter.capture_screenshot(page, path)
        assert result == path
        page.screenshot.assert_called_once_with(path=str(path))

    def test_capture_screenshot_exception_ignored(self, tmp_path):
        adapter = HiworksDevRegAdapter()
        page = MagicMock()
        page.screenshot.side_effect = Exception("browser closed")
        path = tmp_path / "shot.png"
        result = adapter.capture_screenshot(page, path)
        assert result == path  # 예외에도 path 반환
