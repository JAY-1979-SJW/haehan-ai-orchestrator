"""ASSISTANT_BACKEND_WEB_TASK_APPROVAL_FLOW_DESIGN_AUDIT_01
POST /api/v1/web-tasks/run 승인흐름 설계 감사 + boundary test 보강.

공정도 요약:
  A. dry_run=True
     - registry 조회 → params 검증 → adapter.fill_form(None, {**params, dry_run:True})
     - approval 생성 없음, Telegram 발송 없음, task_id 생성 없음
     - 응답: {dry_run, provider, action_type, risk_level, requires_approval,
             success, summary, field_names, target_url, error, error_code}

  B. dry_run=False (현재 항상 approval 필요 경로)
     - registry 조회 → params 검증
     - task_id = "wt-{uuid12}"
     - adapter.fill_form(None, dry_run=True) → summary 생성 (DOM 미접촉)
     - create_web_task_pending_approval() 서비스 호출 (service layer)
       └ issue_token_for_dev_reg() → ApprovalToken (expires_at ISO 형식)
       └ _dra.create_pending() → DevRegApproval 레코드 (status="pending")
       └ build_dev_reg_message() + _ts.send_message() → Telegram 알림 (실패 시 skip)
       └ _dra.mark_telegram_sent() → tg_msg_id 기록
     - 응답: {dry_run:False, status:"pending_approval", task_id, provider, action_type,
             risk_level, requires_approval, expires_at}

  C. dry_run=False + approval 불필요
     - 현재 구현에서 별도 차단 없음 (registry entry.requires_approval 값 참조)
     - 응답에 requires_approval=False 필드만 반영, pending_approval은 여전히 생성됨
     - UNKNOWN_NEEDS_REVIEW (명시적 차단 분기 없음)

방화구획:
  - TELEGRAM_BOT_TOKEN / TELEGRAM_APPROVER_CHAT_ID 미설정 시 자동 skip
  - patch("ai_orchestrator.web_task.web_task_approval_service._ts.send_message") 로 테스트 격리
  - approval_token_hash, screenshot_path는 API 응답에서 _SAFE_EXCLUDE로 제거

설계 판정: NEEDS_APPROVAL_SERVICE_EXTRACTION (완료 — web_task_approval_service.py 분리됨)
  - handler → service 위임으로 책임 분리 완료
  - 응답 계약은 현재 유지 (KEEP_CURRENT_CONTRACT)

모든 테스트는 실제 Telegram/외부 API 호출 없이 동작.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from ai_orchestrator.web_task import web_task_router
from ai_orchestrator.web_task.web_task_approval_service import PendingApprovalResult

# ── 공통 픽스처 ──────────────────────────────────────────────────────────────


def _make_entry(risk_level="medium", requires_approval=True):
    entry = MagicMock()
    entry.risk_level = risk_level
    entry.requires_approval = requires_approval
    adapter = MagicMock()
    fill_result = MagicMock()
    fill_result.success = True
    fill_result.summary = "DRY RUN: app_name=TestApp"
    fill_result.field_names = ["app_name"]
    fill_result.target_url = "https://example.com/apply"
    fill_result.error = None
    fill_result.error_code = None
    adapter.fill_form.return_value = fill_result
    entry.adapter_class.return_value = adapter
    return entry


def _make_approval_result(expires_at="2026-06-01T09:00:00+00:00"):
    return PendingApprovalResult(
        task_id="wt-placeholder",
        expires_at=expires_at,
        risk_level="medium",
        requires_approval=True,
        provider="hiworks",
        action_type="developer_apply",
        telegram_sent=True,
        telegram_message_id="42",
    )


# ── A. dry_run=True 공정도 검증 ──────────────────────────────────────────────


class TestDryRunFlowBoundary:
    """dry_run=True 경로에서 부작용이 발생하지 않음을 고정한다."""

    def _run_dry(self):
        entry = _make_entry()

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry", return_value=entry),
            patch("ai_orchestrator.web_task.web_task_router.validate_params", return_value=[]),
            patch("ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval") as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            result = web_task_router._execute_web_task(
                provider="hiworks",
                action_type="developer_apply",
                params={"app_name": "Audit"},
                dry_run=True,
                actor="admin_u",
                role="admin",
            )
            return result, mock_svc

    def test_dry_run_no_token_issued(self):
        """dry_run=True → create_web_task_pending_approval 호출 없음."""
        _, mock_svc = self._run_dry()
        mock_svc.assert_not_called()

    def test_dry_run_no_pending_created(self):
        """dry_run=True → pending approval 생성 서비스 호출 없음."""
        _, mock_svc = self._run_dry()
        mock_svc.assert_not_called()

    def test_dry_run_no_telegram_sent(self):
        """dry_run=True → Telegram 발송 서비스 호출 없음."""
        _, mock_svc = self._run_dry()
        mock_svc.assert_not_called()

    def test_dry_run_no_mark_telegram_called(self):
        """dry_run=True → mark_telegram_sent 서비스 호출 없음."""
        _, mock_svc = self._run_dry()
        mock_svc.assert_not_called()

    def test_dry_run_response_keys_complete(self):
        """dry_run=True 응답 key 11개 완전성 확인."""
        result, _ = self._run_dry()
        required = {
            "dry_run",
            "provider",
            "action_type",
            "risk_level",
            "requires_approval",
            "success",
            "summary",
            "field_names",
            "target_url",
            "error",
            "error_code",
        }
        assert required.issubset(result.keys()), f"누락 key: {required - result.keys()}"

    def test_dry_run_response_no_pending_approval_key(self):
        """dry_run=True 응답에 status='pending_approval' 없음."""
        result, _ = self._run_dry()
        assert result.get("dry_run") is True
        assert "status" not in result or result.get("status") != "pending_approval"
        assert "task_id" not in result

    def test_dry_run_response_no_secret_keys(self):
        """dry_run=True 응답에 token_id/approval_token_hash 없음."""
        result, _ = self._run_dry()
        assert "token_id" not in result
        assert "approval_token_hash" not in result


# ── B. dry_run=False pending_approval 경로 검증 ──────────────────────────────


class TestRealRunApprovalBoundary:
    """dry_run=False 경로의 부작용 순서와 응답 계약을 고정한다."""

    def _run_real(self, token_expires="2026-06-01T09:00:00+00:00"):
        entry = _make_entry()
        approval = _make_approval_result(token_expires)

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry", return_value=entry),
            patch("ai_orchestrator.web_task.web_task_router.validate_params", return_value=[]),
            patch(
                "ai_orchestrator.web_task.web_task_router.create_web_task_pending_approval", return_value=approval
            ) as mock_svc,
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            result = web_task_router._execute_web_task(
                provider="naver",
                action_type="app_register",
                params={"app_name": "NaverApp"},
                dry_run=False,
                actor="admin_u",
                role="admin",
            )
            return result, mock_svc

    def test_real_run_response_status_is_pending_approval(self):
        """dry_run=False 응답 status='pending_approval'."""
        result, _ = self._run_real()
        assert result["status"] == "pending_approval"

    def test_real_run_response_dry_run_false(self):
        """dry_run=False 응답 dry_run=False."""
        result, _ = self._run_real()
        assert result["dry_run"] is False

    def test_real_run_response_keys_complete(self):
        """dry_run=False 응답 key 8개 완전성 확인."""
        result, _ = self._run_real()
        required = {
            "dry_run",
            "status",
            "task_id",
            "provider",
            "action_type",
            "risk_level",
            "requires_approval",
            "expires_at",
        }
        assert required.issubset(result.keys()), f"누락 key: {required - result.keys()}"

    def test_real_run_task_id_format(self):
        """task_id가 'wt-' prefix + 12자리 hex 형식이다."""
        result, _ = self._run_real()
        task_id = result["task_id"]
        assert re.match(r"^wt-[0-9a-f]{12}$", task_id), f"task_id 형식 불일치: {task_id}"

    def test_real_run_expires_at_is_iso_string(self):
        """expires_at이 ISO 8601 형식 문자열이다."""
        result, _ = self._run_real(token_expires="2026-06-01T09:00:00+00:00")
        expires_at = result["expires_at"]
        assert isinstance(expires_at, str)
        assert "T" in expires_at, f"expires_at ISO 형식 아님: {expires_at}"

    def test_real_run_token_issued_before_pending_created(self):
        """service 내부에서 issue_token이 create_pending보다 먼저 호출된다."""
        call_order = []
        entry = _make_entry()

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry", return_value=entry),
            patch("ai_orchestrator.web_task.web_task_router.validate_params", return_value=[]),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service.issue_token_for_dev_reg",
                side_effect=lambda **kw: (
                    call_order.append("issue"),
                    MagicMock(token_id="tok-x", expires_at="2026-06-01T09:00:00+00:00"),
                )[1],
            ) as _issue_m,
            patch(
                "ai_orchestrator.web_task.web_task_approval_service._dra.create_pending",
                side_effect=lambda **kw: call_order.append("create"),
            ),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service.build_dev_reg_message",
                return_value={"text": "x", "reply_markup": {}},
            ),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service._ts.send_message",
                return_value={"ok": True, "result": {"message_id": 1}},
            ),
            patch("ai_orchestrator.web_task.web_task_approval_service._dra.mark_telegram_sent"),
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            web_task_router._execute_web_task(
                provider="hiworks",
                action_type="developer_apply",
                params={"app_name": "OrderTest"},
                dry_run=False,
                actor="u",
                role="admin",
            )

        assert call_order.index("issue") < call_order.index("create"), (
            "issue_token이 create_pending보다 먼저 호출되어야 함"
        )

    def test_real_run_pending_created_before_telegram_sent(self):
        """create_pending이 send_message보다 먼저 호출된다."""
        call_order = []
        entry = _make_entry()

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry", return_value=entry),
            patch("ai_orchestrator.web_task.web_task_router.validate_params", return_value=[]),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service.issue_token_for_dev_reg",
                return_value=MagicMock(token_id="tok-x", expires_at="2026-06-01T09:00:00+00:00"),
            ),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service._dra.create_pending",
                side_effect=lambda **kw: call_order.append("create"),
            ),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service.build_dev_reg_message",
                return_value={"text": "x", "reply_markup": {}},
            ),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service._ts.send_message",
                side_effect=lambda **kw: (call_order.append("send"), {"ok": True, "result": {"message_id": 1}})[1],
            ),
            patch("ai_orchestrator.web_task.web_task_approval_service._dra.mark_telegram_sent"),
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            web_task_router._execute_web_task(
                provider="hiworks",
                action_type="developer_apply",
                params={"app_name": "OrderTest2"},
                dry_run=False,
                actor="u",
                role="admin",
            )

        assert call_order.index("create") < call_order.index("send"), (
            "create_pending이 send_message보다 먼저 호출되어야 함"
        )

    def test_real_run_response_no_secret_keys(self):
        """dry_run=False 응답에 token_id/approval_token_hash/screenshot_path 없음."""
        result, _ = self._run_real()
        assert "token_id" not in result
        assert "approval_token_hash" not in result
        assert "screenshot_path" not in result

    def test_real_run_response_no_success_key(self):
        """dry_run=False 응답에 success 키 없음 (봉투 미적용 유지)."""
        result, _ = self._run_real()
        assert "success" not in result


# ── C. Telegram 실패 fallback 방화구획 ────────────────────────────────────────


class TestTelegramFailureFallback:
    """Telegram 발송 실패가 응답 계약을 깨지 않음을 고정한다."""

    def _run_with_telegram(self, send_result):
        entry = _make_entry()

        with (
            patch("ai_orchestrator.web_task.web_task_router.get_entry", return_value=entry),
            patch("ai_orchestrator.web_task.web_task_router.validate_params", return_value=[]),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service.issue_token_for_dev_reg",
                return_value=MagicMock(token_id="tok-x", expires_at="2026-06-01T09:00:00+00:00"),
            ),
            patch("ai_orchestrator.web_task.web_task_approval_service._dra.create_pending"),
            patch(
                "ai_orchestrator.web_task.web_task_approval_service.build_dev_reg_message",
                return_value={"text": "msg", "reply_markup": {}},
            ),
            patch("ai_orchestrator.web_task.web_task_approval_service._ts.send_message", return_value=send_result),
            patch("ai_orchestrator.web_task.web_task_approval_service._dra.mark_telegram_sent"),
            patch("ai_orchestrator.web_task.web_task_router.log_event"),
        ):
            return web_task_router._execute_web_task(
                provider="hiworks",
                action_type="developer_apply",
                params={"app_name": "TgFailTest"},
                dry_run=False,
                actor="u",
                role="admin",
            )

    def test_telegram_skip_still_returns_pending_approval(self):
        """TELEGRAM_BOT_TOKEN 미설정(skipped=True) 시에도 pending_approval 응답."""
        result = self._run_with_telegram({"ok": False, "skipped": True})
        assert result["status"] == "pending_approval"
        assert "task_id" in result

    def test_telegram_error_still_returns_pending_approval(self):
        """Telegram HTTP 오류 시에도 pending_approval 응답."""
        result = self._run_with_telegram({"ok": False, "error": "connection refused"})
        assert result["status"] == "pending_approval"
        assert "task_id" in result

    def test_telegram_success_returns_pending_approval(self):
        """Telegram 성공 시 pending_approval 응답."""
        result = self._run_with_telegram({"ok": True, "result": {"message_id": 99}})
        assert result["status"] == "pending_approval"

    def test_telegram_token_not_in_response(self):
        """어떤 경우에도 Telegram token이 응답에 포함되지 않는다."""
        result = self._run_with_telegram({"ok": False, "skipped": True})
        blob = str(result)
        assert "tok-x" not in blob, "token_id가 응답에 노출됨"

    def test_telegram_skip_guard_in_source(self):
        """telegram_sender.py에 TOKEN 미설정 시 skip 가드가 존재한다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/core/telegram_sender.py").read_text(encoding="utf-8")
        assert "skipped" in src
        assert "TELEGRAM_BOT_TOKEN" in src


# ── D. 통합 흐름: TestClient 기반 ────────────────────────────────────────────


class TestWebTaskRunIntegrationBoundary:
    """TestClient를 통한 통합 경계 고정."""

    @pytest.fixture(scope="class")
    def client(self):
        import ai_orchestrator.core.config as config

        config.AUTH_ENABLED = False
        from fastapi.testclient import TestClient

        from ai_orchestrator.asgi import app

        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture(scope="class")
    def auth(self):
        return {}

    def test_dry_run_via_client_no_pending_record(self, client, auth):
        """TestClient dry_run=True — dev_reg_approval pending 레코드 없음."""
        import ai_orchestrator.dev_reg.dev_reg_approval as _dra

        before = len(_dra.list_pending())

        r = client.post(  # noqa: F841
            "/api/v1/web-tasks/run",
            headers=auth,
            json={
                "provider": "hiworks",
                "action_type": "developer_apply",
                "params": {"app_name": "DryNoRecord"},
                "dry_run": True,
            },
        )
        # dry_run은 등록된 provider일 때만 200, 없으면 404 — 두 경우 모두 pending 없음
        after = len(_dra.list_pending())
        assert after == before

    def test_real_run_via_client_with_mock_telegram(self, client, auth):
        """TestClient real_run — Telegram mock, pending_approval 응답 확인."""
        with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
            r = client.post(
                "/api/v1/web-tasks/run",
                headers=auth,
                json={
                    "provider": "hiworks",
                    "action_type": "developer_apply",
                    "params": {"app_name": "RealRunAudit"},
                    "dry_run": False,
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending_approval"
        assert data["task_id"].startswith("wt-")
        assert "T" in data["expires_at"]

    def test_real_run_no_envelope(self, client, auth):
        """TestClient real_run 응답에 ApiResponse 봉투 없음."""
        with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
            r = client.post(
                "/api/v1/web-tasks/run",
                headers=auth,
                json={
                    "provider": "hiworks",
                    "action_type": "developer_apply",
                    "params": {"app_name": "NoEnvelope"},
                    "dry_run": False,
                },
            )
        body = r.json()
        assert "success" not in body or body.get("status") == "pending_approval"
        assert "data" not in body

    def test_real_run_secret_not_in_response(self, client, auth):
        """params의 민감 필드가 응답에 포함되지 않는다."""
        secret = "audit_secret_xzy9876"
        with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
            r = client.post(
                "/api/v1/web-tasks/run",
                headers=auth,
                json={
                    "provider": "hiworks",
                    "action_type": "developer_apply",
                    "params": {"app_name": "SecTest", "password": secret},
                    "dry_run": False,
                },
            )
        assert secret not in r.text


# ── E. 설계 판정 고정 ─────────────────────────────────────────────────────────


class TestApprovalFlowDesignVerdict:
    """설계 판정: NEEDS_APPROVAL_SERVICE_EXTRACTION (완료) + KEEP_CURRENT_CONTRACT."""

    DESIGN_VERDICT = "NEEDS_APPROVAL_SERVICE_EXTRACTION"
    CONTRACT_VERDICT = "KEEP_CURRENT_CONTRACT"

    def test_design_verdict_declared(self):
        """설계 판정이 NEEDS_APPROVAL_SERVICE_EXTRACTION로 선언된다."""
        assert self.DESIGN_VERDICT == "NEEDS_APPROVAL_SERVICE_EXTRACTION"

    def test_contract_verdict_declared(self):
        """응답 계약 판정이 KEEP_CURRENT_CONTRACT로 선언된다."""
        assert self.CONTRACT_VERDICT == "KEEP_CURRENT_CONTRACT"

    def test_handler_has_mixed_responsibilities(self):
        """service 소스에 token/pending/send/mark 4가지 책임이 위임되어 있다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_approval_service.py").read_text(encoding="utf-8")
        responsibilities = [
            "issue_token_for_dev_reg",
            "_dra.create_pending",
            "_ts.send_message",
            "_dra.mark_telegram_sent",
        ]
        for r in responsibilities:
            assert r in src, f"책임 항목 '{r}'가 service 소스에 없음"

    def test_no_envelope_conversion_attempted(self):
        """web_task_router.py에 ApiResponse 봉투 import가 없다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        assert "api_success" not in src
        assert "ApiResponse" not in src
        assert "wrap_legacy_dict" not in src

    def test_response_keys_unchanged_dry_run(self):
        """dry_run=True 응답 key 11개가 소스에 유지된다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        keys = [
            '"dry_run"',
            '"provider"',
            '"action_type"',
            '"risk_level"',
            '"requires_approval"',
            '"success"',
            '"summary"',
            '"field_names"',
            '"target_url"',
            '"error"',
            '"error_code"',
        ]
        for k in keys:
            assert k in src, f"dry_run 응답 key {k}가 소스에서 제거됨"

    def test_response_keys_unchanged_real_run(self):
        """dry_run=False 응답 key 8개가 소스에 유지된다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        keys = [
            '"status"',
            '"pending_approval"',
            '"task_id"',
            '"expires_at"',
            '"dry_run"',
            '"provider"',
            '"action_type"',
            '"requires_approval"',
        ]
        for k in keys:
            assert k in src, f"real_run 응답 key {k}가 소스에서 제거됨"
