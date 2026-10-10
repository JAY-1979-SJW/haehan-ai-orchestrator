"""web_task_router.py 정책 흐름 통합 테스트 (Stage 4B).

dry_run / params validation / safe param filtering / approval flow
각 경로에서 mock 기반으로 정책 강제를 검증한다.
실제 브라우저/외부 사이트 접근은 발생하지 않고, adapter/approval/telegram은 mock으로 확인한다.
"""

from unittest.mock import MagicMock, patch

import pytest

from ai_orchestrator.web_task import web_task_router


class TestWebTaskRouterDryRunPath:
    """A. dry_run=True 정책 검증"""

    def test_dry_run_calls_adapter_with_none_page(self):
        """dry_run=True 시 adapter.fill_form(None, params+dry_run=True) 호출"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test summary"
        mock_result.field_names = []
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "low"
        mock_entry.requires_approval = False

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            result = web_task_router._execute_web_task(  # noqa: F841
                provider="test_provider",
                action_type="test_action",
                params={"key": "value"},
                dry_run=True,
                actor="test_user",
                role="admin",
            )

            # adapter 호출 확인
            mock_adapter.fill_form.assert_called_once()
            call_args = mock_adapter.fill_form.call_args
            assert call_args[0][0] is None  # page=None
            assert call_args[0][1].get("dry_run") is True

    def test_dry_run_no_approval_token_issued(self):
        """dry_run=True 시 approval service 호출 금지 (token/pending/telegram 모두 없음)"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test"
        mock_result.field_names = []
        mock_result.target_url = "http://test.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "low"
        mock_entry.requires_approval = False

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={},
                dry_run=True,
                actor="user",
                role="admin",
            )

            mock_svc.assert_not_called()

    def test_dry_run_no_pending_record_created(self):
        """dry_run=True 시 approval service 미호출 → pending 레코드 생성 없음"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test"
        mock_result.field_names = []
        mock_result.target_url = "http://test.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "low"
        mock_entry.requires_approval = False

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={},
                dry_run=True,
                actor="user",
                role="admin",
            )

            mock_svc.assert_not_called()

    def test_dry_run_no_telegram_notification(self):
        """dry_run=True 시 approval service 미호출 → Telegram 알림 없음"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test"
        mock_result.field_names = []
        mock_result.target_url = "http://test.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "low"
        mock_entry.requires_approval = False

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_approval_service._ts.send_message") as mock_send,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={},
                dry_run=True,
                actor="user",
                role="admin",
            )

            mock_svc.assert_not_called()
            mock_send.assert_not_called()

    def test_dry_run_response_structure(self):
        """dry_run=True 응답 구조 검증"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "dry run summary"
        mock_result.field_names = ["field1", "field2"]
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "medium"
        mock_entry.requires_approval = True

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            result = web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={"test": "value"},
                dry_run=True,
                actor="user",
                role="admin",
            )

            assert result["dry_run"] is True
            assert result["success"] is True
            assert result["summary"] == "dry run summary"
            assert result["field_names"] == ["field1", "field2"]
            assert "pending_approval" not in str(result.get("status", ""))


class TestWebTaskRouterRealRunPath:
    """B. dry_run=False pending approval 경로"""

    def _mock_approval_result(self, expires_at="2026-04-28T10:00:00Z"):
        from ai_orchestrator.web_task.web_task_approval_service import PendingApprovalResult

        return PendingApprovalResult(
            task_id="wt-placeholder",
            expires_at=expires_at,
            risk_level="medium",
            requires_approval=True,
            provider="test",
            action_type="test",
            telegram_sent=False,
            telegram_message_id="",
        )

    def test_real_run_issues_token(self):
        """dry_run=False 시 approval service 호출 (내부적으로 token 발행)"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test summary"
        mock_result.field_names = []
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "medium"
        mock_entry.requires_approval = True

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []
            mock_svc.return_value = self._mock_approval_result()

            web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={},
                dry_run=False,
                actor="user",
                role="admin",
            )

            mock_svc.assert_called_once()

    def test_real_run_creates_pending_record(self):
        """dry_run=False 시 approval service가 호출됨 (내부적으로 pending 생성)"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test summary"
        mock_result.field_names = []
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "medium"
        mock_entry.requires_approval = True

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []
            mock_svc.return_value = self._mock_approval_result()

            web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={},
                dry_run=False,
                actor="user",
                role="admin",
            )

            mock_svc.assert_called_once()
            call_kwargs = mock_svc.call_args[1]
            assert "task_id" in call_kwargs
            assert "provider" in call_kwargs
            assert "action_type" in call_kwargs

    def test_real_run_returns_pending_approval(self):
        """dry_run=False 응답에 pending_approval 상태 포함"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test summary"
        mock_result.field_names = []
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "medium"
        mock_entry.requires_approval = True

        approval_result = self._mock_approval_result("2026-04-28T10:00:00Z")

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch(
                "ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval", return_value=approval_result
            ),
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            result = web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params={},
                dry_run=False,
                actor="user",
                role="admin",
            )

            assert result["dry_run"] is False
            assert result["status"] == "pending_approval"
            assert "task_id" in result
            assert result["expires_at"] == "2026-04-28T10:00:00Z"


class TestWebTaskRouterParamsValidation:
    """C. params 검증 실패"""

    def test_validation_failure_no_approval(self):
        """params 검증 실패 시 approval token 발행 금지"""
        mock_entry = MagicMock()
        mock_entry.adapter_class.return_value = MagicMock()

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = ["validation_error"]

            with pytest.raises(Exception):  # HTTPException 또는 유사  # noqa: B017
                web_task_router._execute_web_task(
                    provider="test",
                    action_type="test",
                    params={},
                    dry_run=False,
                    actor="user",
                    role="admin",
                )

            mock_svc.assert_not_called()

    def test_validation_failure_no_adapter_execution(self):
        """params 검증 실패 시 adapter 실행 금지"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_entry.adapter_class.return_value = mock_adapter

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = ["error1", "error2"]

            with pytest.raises(Exception):  # noqa: B017
                web_task_router._execute_web_task(
                    provider="test",
                    action_type="test",
                    params={},
                    dry_run=False,
                    actor="user",
                    role="admin",
                )

            mock_adapter.fill_form.assert_not_called()


class TestWebTaskRouterSafeParamFiltering:
    """D. 민감한 파라미터 필터링"""

    def test_safe_params_only_in_audit_log(self):
        """감사 로그에는 _SAFE_PARAM_KEYS만 기록"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test"
        mock_result.field_names = []
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "low"
        mock_entry.requires_approval = False

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.log_event") as mock_log,
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            params = {
                "app_name": "MyApp",
                "secret_key": "SECRET123",
                "api_token": "TOKEN456",
                "password": "PASS789",
            }

            web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params=params,
                dry_run=True,
                actor="user",
                role="admin",
            )

            # log_event 호출 확인
            if mock_log.called:
                # 민감한 파라미터가 로그에 노출되지 않음을 확인
                log_calls = str(mock_log.call_args_list)
                # app_name은 SAFE_PARAM_KEYS에 포함되므로 로그 가능
                # secret_key, api_token, password는 포함되지 않음
                assert "SECRET123" not in log_calls or "secret_key" not in log_calls
                assert "TOKEN456" not in log_calls or "api_token" not in log_calls
                assert "PASS789" not in log_calls or "password" not in log_calls

    def test_safe_params_in_response(self):
        """응답에 원본 파라미터 노출 금지"""
        mock_entry = MagicMock()
        mock_adapter = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "test"
        mock_result.field_names = []
        mock_result.target_url = "http://example.com"
        mock_result.error = None
        mock_result.error_code = None

        mock_adapter.fill_form.return_value = mock_result
        mock_entry.adapter_class.return_value = mock_adapter
        mock_entry.risk_level = "low"
        mock_entry.requires_approval = False

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry") as mock_get_entry,
            patch("ai_orchestrator.web_task.web_task_router.validate_params") as mock_validate,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            mock_get_entry.return_value = mock_entry
            mock_validate.return_value = []

            params = {
                "app_name": "MyApp",
                "secret_api_key": "SECRET",
                "token": "TOKEN",
            }

            result = web_task_router._execute_web_task(
                provider="test",
                action_type="test",
                params=params,
                dry_run=True,
                actor="user",
                role="admin",
            )

            # 응답 확인
            result_str = str(result)
            assert "SECRET" not in result_str or "secret_api_key" not in result_str
            assert "TOKEN" not in result_str or "token" not in result_str
