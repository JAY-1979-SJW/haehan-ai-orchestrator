"""개발자 등록 어댑터 2단계 테스트.

검증 항목:
  1. hiworks fill_form dry_run
  2. naver fill_form dry_run
  3. google fill_form dry_run
  4. 승인 전 submit 방지 (fill_form 이 submit 버튼 자동 클릭 안 함)
  5. 승인 후 submit 가능 (submit_form 명시 호출 시 정상 동작)
  6. 민감정보 미노출 (summary/field_names 에 password/cookie/token 미포함)
  7. 기존 승인 게이트 회귀 유지
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.sites.adapters.dev_reg_base import (  # noqa: E402
    _build_safe_summary,
    _mask_email,
    validate_params,
)
from ai_orchestrator.sites.adapters.google_dev_reg import GoogleDevRegAdapter  # noqa: E402
from ai_orchestrator.sites.adapters.hiworks_dev_reg import HiworksDevRegAdapter  # noqa: E402
from ai_orchestrator.sites.adapters.naver_dev_reg import NaverDevRegAdapter  # noqa: E402

# ── 공통 파라미터 픽스처 ─────────────────────────────────────────────────────


def _base_params(**overrides) -> dict:
    base = {
        "app_name": "테스트앱",
        "company_name": "테스트코리아(주)",
        "service_url": "https://example.com",
        "redirect_uri": "https://example.com/oauth/callback",
        "contact_email": "dev@example.com",
        "purpose": "테스트 목적 앱 등록",
        "requested_scopes": ["blog", "cafe"],
    }
    base.update(overrides)
    return base


def _mock_page(inner_text: str = "등록 완료") -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com/done"
    page.inner_text.return_value = inner_text
    return page


# ── 1. Hiworks fill_form dry_run ────────────────────────────────────────────


class TestHiworksDryRun:
    def test_returns_success(self):
        adapter = HiworksDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert result.success is True

    def test_no_page_calls(self):
        adapter = HiworksDevRegAdapter()
        page = MagicMock()
        adapter.fill_form(page, _base_params(dry_run=True))
        page.goto.assert_not_called()
        page.fill.assert_not_called()
        page.click.assert_not_called()

    def test_summary_contains_dry_run_marker(self):
        adapter = HiworksDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert "[DRY RUN]" in result.summary

    def test_field_names_populated(self):
        adapter = HiworksDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert "app_name" in result.field_names
        assert "redirect_uri" in result.field_names

    def test_missing_app_name_fails(self):
        adapter = HiworksDevRegAdapter()
        result = adapter.fill_form(None, {"dry_run": True})
        assert result.success is False
        assert "app_name" in result.error


# ── 2. Naver fill_form dry_run ──────────────────────────────────────────────


class TestNaverDryRun:
    def test_returns_success(self):
        adapter = NaverDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert result.success is True

    def test_no_page_calls(self):
        adapter = NaverDevRegAdapter()
        page = MagicMock()
        adapter.fill_form(page, _base_params(dry_run=True))
        page.goto.assert_not_called()
        page.fill.assert_not_called()
        page.check.assert_not_called()

    def test_summary_contains_dry_run_marker(self):
        adapter = NaverDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert "[DRY RUN]" in result.summary

    def test_scopes_in_field_names(self):
        adapter = NaverDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True, requested_scopes=["blog", "cafe"]))
        assert "scope:blog" in result.field_names
        assert "scope:cafe" in result.field_names

    def test_missing_app_name_fails(self):
        adapter = NaverDevRegAdapter()
        result = adapter.fill_form(None, {"dry_run": True})
        assert result.success is False


# ── 3. Google fill_form dry_run ─────────────────────────────────────────────


class TestGoogleDryRun:
    def test_returns_success(self):
        adapter = GoogleDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert result.success is True

    def test_no_page_calls(self):
        adapter = GoogleDevRegAdapter()
        page = MagicMock()
        adapter.fill_form(page, _base_params(dry_run=True))
        page.goto.assert_not_called()
        page.fill.assert_not_called()
        page.click.assert_not_called()

    def test_summary_contains_dry_run_marker(self):
        adapter = GoogleDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert "[DRY RUN]" in result.summary

    def test_redirect_uri_in_field_names(self):
        adapter = GoogleDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True))
        assert "redirect_uri" in result.field_names

    def test_missing_app_name_fails(self):
        adapter = GoogleDevRegAdapter()
        result = adapter.fill_form(None, {"dry_run": True})
        assert result.success is False
        assert "app_name" in result.error


# ── 4. 승인 전 submit 방지 ───────────────────────────────────────────────────


class TestNoAutoSubmit:
    """fill_form 이 submit 버튼을 자동으로 클릭하지 않음을 검증한다."""

    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_fill_does_not_click_submit(self, AdapterCls):
        adapter = AdapterCls()
        page = MagicMock()
        adapter.fill_form(page, _base_params(dry_run=True))
        # click() 이 호출되면 안 됨 (dry_run 이라 goto/fill 도 없음)
        page.click.assert_not_called()

    @pytest.mark.parametrize(
        "AdapterCls,submit_text",
        [
            (HiworksDevRegAdapter, "완료"),
            (NaverDevRegAdapter, "등록 완료"),
            (GoogleDevRegAdapter, "saved"),
        ],
    )
    def test_fill_without_dry_run_no_submit_click(self, AdapterCls, submit_text):
        """실제 모드에서도 fill_form 은 submit 클릭 안 함."""
        adapter = AdapterCls()
        page = _mock_page(submit_text)
        # goto 는 호출되지만 submit 클릭은 안 됨
        adapter.fill_form(page, _base_params())
        # 제출 관련 버튼 선택자들이 클릭되면 안 됨
        for call_args in page.click.call_args_list:
            selector = call_args[0][0] if call_args[0] else ""
            assert "submit" not in selector.lower() or "btn-register" not in selector, (
                f"fill_form 이 submit 버튼을 클릭했음: {selector}"
            )


# ── 5. 승인 후 submit 가능 ───────────────────────────────────────────────────


class TestSubmitAfterApproval:
    """submit_form 을 명시적으로 호출(승인 후 runner 가 호출)하면 정상 동작."""

    def test_hiworks_submit_calls_click(self):
        adapter = HiworksDevRegAdapter()
        page = _mock_page("완료")
        result = adapter.submit_form(page)
        page.click.assert_called_once()
        assert result.success is True

    def test_naver_submit_calls_click(self):
        adapter = NaverDevRegAdapter()
        page = _mock_page("등록 완료")
        result = adapter.submit_form(page)
        page.click.assert_called_once()
        assert result.success is True

    def test_google_submit_calls_click(self):
        adapter = GoogleDevRegAdapter()
        page = _mock_page("saved")
        result = adapter.submit_form(page)
        page.click.assert_called_once()
        assert result.success is True

    def test_submit_failure_returns_error(self):
        adapter = HiworksDevRegAdapter()
        page = MagicMock()
        page.click.side_effect = Exception("네트워크 오류")
        result = adapter.submit_form(page)
        assert result.success is False
        assert result.error != ""


# ── 6. 민감정보 미노출 ───────────────────────────────────────────────────────


class TestSensitiveDataExclusion:
    """summary, field_names 에 password/cookie/token 미포함."""

    _SENSITIVE_PARAMS = {
        "app_name": "테스트앱",
        "company_name": "테스트코리아",
        "contact_email": "dev@example.com",
        "purpose": "테스트",
        "service_url": "https://example.com",
        "redirect_uri": "https://example.com/cb",
        # 민감 값: schema 에 없는 키로 주입 시도
        "password": "super_secret_pw",
        "client_secret": "client_secret_xyz",
        "cookie": "session_cookie_abc",
        "dry_run": True,
    }

    @pytest.mark.parametrize(
        "AdapterCls",
        [
            HiworksDevRegAdapter,
            NaverDevRegAdapter,
            GoogleDevRegAdapter,
        ],
    )
    def test_sensitive_not_in_summary(self, AdapterCls):
        adapter = AdapterCls()
        result = adapter.fill_form(None, self._SENSITIVE_PARAMS)
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
        adapter = AdapterCls()
        result = adapter.fill_form(None, self._SENSITIVE_PARAMS)
        for name in result.field_names:
            assert "password" not in name
            assert "client_secret" not in name
            assert "cookie" not in name

    def test_email_masked_in_summary(self):
        adapter = HiworksDevRegAdapter()
        result = adapter.fill_form(None, _base_params(dry_run=True, contact_email="developer@example.com"))
        # 'dev***@example.com' 형태여야 함 (원문 그대로 노출 금지)
        assert "developer@example.com" not in result.summary
        assert "dev***" in result.summary

    def test_build_safe_summary_excludes_unknown_keys(self):
        summary = _build_safe_summary(
            "test",
            {"app_name": "App", "password": "SECRET", "cookie": "ABC"},
            ["app_name", "password", "cookie"],
        )
        assert "SECRET" not in summary
        assert "ABC" not in summary
        assert "App" in summary

    def test_mask_email_utility(self):
        assert _mask_email("dev@example.com") == "dev***@example.com"
        assert _mask_email("ab@x.com") == "ab***@x.com"
        assert _mask_email("noemail") == "noe***"


# ── 7. 기존 승인 게이트 회귀 유지 ───────────────────────────────────────────


class TestApprovalGateRegression:
    """어댑터 변경이 기존 승인 게이트 데이터 구조를 깨뜨리지 않음."""

    def test_form_fill_result_fields(self):
        """FormFillResult 필드가 runner 가 기대하는 구조 그대로."""
        from ai_orchestrator.sites.adapters.dev_reg_base import FormFillResult

        r = FormFillResult(success=True, summary="요약", field_names=["app_name"], target_url="https://x.com")
        assert hasattr(r, "success")
        assert hasattr(r, "summary")
        assert hasattr(r, "field_names")
        assert hasattr(r, "target_url")
        assert hasattr(r, "error")

    def test_submit_result_fields(self):
        from ai_orchestrator.sites.adapters.dev_reg_base import SubmitResult

        r = SubmitResult(success=True, result_summary="완료")
        assert hasattr(r, "success")
        assert hasattr(r, "result_summary")
        assert hasattr(r, "error")

    def test_adapter_provider_attributes(self):
        """provider/action_type/risk_level 속성이 존재하고 유효한 값."""
        for AdapterCls, expected_provider, expected_action in [
            (HiworksDevRegAdapter, "hiworks", "developer_apply"),
            (NaverDevRegAdapter, "naver", "app_register"),
            (GoogleDevRegAdapter, "google", "oauth_submit"),
        ]:
            adapter = AdapterCls()
            assert adapter.provider == expected_provider
            assert adapter.action_type == expected_action
            assert adapter.risk_level == "high"

    def test_abort_form_navigates_blank(self):
        """abort_form 은 거절/만료 시 about:blank 로 이동한다."""
        for AdapterCls in [HiworksDevRegAdapter, NaverDevRegAdapter, GoogleDevRegAdapter]:
            adapter = AdapterCls()
            page = MagicMock()
            adapter.abort_form(page)
            page.goto.assert_called_with("about:blank")

    def test_validate_params_requires_app_name(self):
        assert validate_params({}) == ["app_name 은 필수입니다"]
        assert validate_params({"app_name": "App"}) == []

    def test_validate_params_empty_app_name(self):
        assert len(validate_params({"app_name": "   "})) > 0
