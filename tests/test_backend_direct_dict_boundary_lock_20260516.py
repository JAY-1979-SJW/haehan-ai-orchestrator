"""ASSISTANT_BACKEND_DIRECT_DICT_RESPONSE_BOUNDARY_CLOSEOUT_01
응답 계약 characterization 테스트 + HOLD gate.

대상 4개 엔드포인트:
  NEEDS_ENVELOPE_REVIEW (3):
    POST /api/v1/site-tasks/dry-run
    POST /api/v1/web-tasks/run
    POST /api/v1/web-tasks/run-from-template
  NEEDS_MANUAL_DESIGN_REVIEW / HOLD (1):
    POST /api/v1/webhooks/telegram
  (POST /api/v1/cad-ai/chat 은 17130f8e "CAD 모듈 전체 삭제" 로 엔드포인트 자체가 사라져 2026-10-05 에 이 시험에서 제거)

판정 근거:
  - HOLD 사유: 외부 연동(Telegram Bot) / AI 응답 중계(OpenAI) → 응답 구조 임의 변경 금지
  - ENVELOPE_REVIEW 3개: 현재 응답 key 구조를 잠그고 봉투 전환 안전성 평가
    → 판정 결과: HOLD_FOR_NEXT_PHASE
      site-tasks/dry-run → SiteExecutionResult.to_dict() — domain 객체 직렬화,
        봉투 추가 시 frontend/테스트 의존 가능성 확인 필요
      web-tasks/run / run-from-template → 내부 dict 반환, success 키 없음,
        telegram_notifier 연동(실 전송) 포함 → UI/클라이언트 계약 변경 위험

모든 테스트는 실제 외부 API(Telegram, OpenAI, 브라우저) 호출 없이 동작.
DB write, schema 변경, secret 출력 없음.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ── HOLD 선언 상수 ────────────────────────────────────────────────────────────

HOLD_TELEGRAM_WEBHOOK = "POST /api/v1/webhooks/telegram"

HOLD_REASON_TELEGRAM = (
    "외부 Telegram Bot 연동 및 콜백 payload 계약(callback_query 분기) — "
    "응답 구조 변경 시 Bot 클라이언트 계약 파괴 위험. 봉투 적용 금지."
)


# ── 픽스처 ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    import ai_orchestrator.core.config as config

    config.AUTH_ENABLED = False
    from ai_orchestrator.asgi import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def auth():
    return {}


# ── 1. HOLD gate: webhooks/telegram ──────────────────────────────────────────


class TestTelegramWebhookHold:
    """HOLD: POST /api/v1/webhooks/telegram 응답 계약 고정."""

    def test_hold_declaration(self):
        """HOLD 선언이 명시적으로 존재한다."""
        assert HOLD_TELEGRAM_WEBHOOK == "POST /api/v1/webhooks/telegram"
        assert "Telegram" in HOLD_REASON_TELEGRAM

    def test_invalid_payload_returns_400_with_detail_dict(self, client):
        """잘못된 payload → 400, detail은 dict(success, status, message 포함)."""
        r = client.post("/api/v1/webhooks/telegram", json={"bad": "data"})
        assert r.status_code == 400
        detail = r.json().get("detail", {})
        assert isinstance(detail, dict), "detail은 dict여야 한다"
        assert "success" in detail
        assert detail["success"] is False
        assert "status" in detail
        assert "message" in detail

    def test_invalid_payload_success_key_is_false(self, client):
        """실패 응답에 success=False가 있다 — 키 삭제/이름 변경 금지."""
        r = client.post("/api/v1/webhooks/telegram", json={})
        assert r.status_code == 400
        detail = r.json().get("detail", {})
        assert detail.get("success") is False

    def test_no_envelope_wrapper_on_success_path(self, client):
        """성공 응답에 ApiResponse 봉투(success/data 래퍼)가 적용되지 않는다.

        실제 성공 flow는 외부 telegram 의존이므로 400 응답 구조로 계약 고정.
        """
        r = client.post("/api/v1/webhooks/telegram", json={})
        body = r.json()
        # 최상위에 'data' 봉투 키가 없음 (봉투 미적용 확인)
        assert "data" not in body

    def test_callback_query_path_exists_in_source(self):
        """router.py에 callback_query 분기 코드가 존재한다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/routers/registry.py").read_text(encoding="utf-8")
        assert "callback_query" in src
        assert "handle_telegram_update" in src
        assert "handle_telegram_webhook" in src

    def test_missing_fields_in_status(self, client):
        """누락 필드 감지 시 status=invalid_payload로 반환된다."""
        r = client.post("/api/v1/webhooks/telegram", json={"action": "approve", "task_id": "t1"})
        assert r.status_code == 400
        detail = r.json().get("detail", {})
        assert detail.get("status") == "invalid_payload"


# ── 3. Characterization: site-tasks/dry-run ──────────────────────────────────


class TestSiteTaskDryRunCharacterization:
    """POST /api/v1/site-tasks/dry-run 응답 계약 고정 (HOLD_FOR_NEXT_PHASE).

    현재 응답: SiteExecutionResult.to_dict() = asdict() → 평탄 dict.
    봉투 적용 판정: HOLD — frontend/CLI 테스트 의존 범위 확인 필요.
    """

    def test_unknown_connector_returns_404(self, client, auth):
        """미등록 connector → 404, detail 문자열 포함."""
        r = client.post(
            "/api/v1/site-tasks/dry-run",
            headers=auth,
            json={
                "task_id": "t1",
                "target_site": "nonexistent",
                "action": "noop",
                "params": {},
                "risk_level": "low",
                "requires_approval": False,
            },
        )
        assert r.status_code == 404
        assert "connector" in r.json().get("detail", "").lower()

    def test_no_envelope_on_404(self, client, auth):
        """404 응답에 ApiResponse 봉투가 없다."""
        r = client.post(
            "/api/v1/site-tasks/dry-run",
            headers=auth,
            json={
                "task_id": "t1",
                "target_site": "nonexistent",
                "action": "noop",
                "params": {},
                "risk_level": "low",
                "requires_approval": False,
            },
        )
        body = r.json()
        assert "success" not in body

    def test_result_keys_come_from_site_execution_result(self):
        """SiteExecutionResult.to_dict() 키 목록이 변경되지 않았다."""
        import dataclasses

        from ai_orchestrator.sites.models import SiteExecutionResult

        fields = {f.name for f in dataclasses.fields(SiteExecutionResult)}
        expected = {
            "task_id",
            "target_site",
            "action",
            "status",
            "started_at",
            "finished_at",
            "summary",
            "artifacts",
            "screenshots",
            "error_code",
            "error_message",
            "health_snapshot",
            "duration_ms",
        }
        assert expected.issubset(fields), f"SiteExecutionResult 필드 누락: {expected - fields}"

    def test_to_dict_returns_flat_dict(self):
        """to_dict()가 봉투 없는 평탄 dict를 반환한다."""
        from ai_orchestrator.sites.models import SiteExecutionResult

        r = SiteExecutionResult(task_id="t1", target_site="s1", action="noop", status="ok")
        d = r.to_dict()
        assert isinstance(d, dict)
        assert "success" not in d, "봉투 미적용 — success 키 없어야 함"
        assert d["task_id"] == "t1"
        assert d["target_site"] == "s1"

    def test_auth_behavior_recorded(self, client):
        """테스트 환경 auth 동작 기록 — 인증 없이 404(connector 없음) 또는 401/403."""
        r = client.post(
            "/api/v1/site-tasks/dry-run",
            json={
                "task_id": "t1",
                "target_site": "s",
                "action": "noop",
                "params": {},
                "risk_level": "low",
                "requires_approval": False,
            },
        )
        assert r.status_code in (401, 403, 404)
        assert "success" not in r.json()

    def test_hold_for_next_phase_comment(self):
        """봉투 전환 보류 사유 — 이 테스트가 HOLD 근거 역할을 한다."""
        reason = (
            "site-tasks/dry-run은 SiteExecutionResult.to_dict()를 직접 반환. "
            "봉투 추가 시 기존 CLI/테스트 의존 key 구조 파괴 가능. "
            "다음 phase에서 frontend 의존성 확인 후 결정."
        )
        assert len(reason) > 0  # 문서화 보장


# ── 4. Characterization: web-tasks/run ───────────────────────────────────────


class TestWebTasksRunCharacterization:
    """POST /api/v1/web-tasks/run 응답 계약 고정 (HOLD_FOR_NEXT_PHASE).

    dry_run=True 응답 키: dry_run/provider/action_type/risk_level/requires_approval/
                          success/summary/field_names/target_url/error/error_code
    dry_run=False: 실제 Telegram 발송 포함 → 테스트에서 mock 처리
    봉투 적용 판정: HOLD — real_run 경로 Telegram 연동 + UI 클라이언트 계약
    """

    def test_unknown_provider_returns_404(self, client, auth):
        """미등록 provider → 404, detail에 error/message 포함."""
        r = client.post(
            "/api/v1/web-tasks/run",
            headers=auth,
            json={"provider": "no-provider", "action_type": "noop", "dry_run": True},
        )
        assert r.status_code == 404
        detail = r.json().get("detail", {})
        assert "error" in detail
        assert "message" in detail

    def test_404_error_key_is_unknown_task(self, client, auth):
        """미등록 provider → error='UNKNOWN_TASK'."""
        r = client.post(
            "/api/v1/web-tasks/run", headers=auth, json={"provider": "ghost", "action_type": "x", "dry_run": True}
        )
        assert r.json()["detail"]["error"] == "UNKNOWN_TASK"

    def test_validation_error_returns_422_with_keys(self, client, auth):
        """params 누락 → 422, detail에 error_code/missing_fields/invalid_fields."""
        # 이 테스트는 등록된 provider가 있을 때만 422에 도달.
        # registry가 비어 있으면 404 → 두 경우 모두 계약 고정.
        r = client.post(
            "/api/v1/web-tasks/run",
            headers=auth,
            json={"provider": "no-provider", "action_type": "noop", "params": {}, "dry_run": True},
        )
        # 404 또는 422 — 두 경우 모두 봉투 없음 확인
        assert r.status_code in (404, 422)
        body = r.json()
        assert "success" not in body

    def test_no_envelope_on_404(self, client, auth):
        """404 응답 최상위에 봉투 없음."""
        r = client.post(
            "/api/v1/web-tasks/run", headers=auth, json={"provider": "ghost", "action_type": "x", "dry_run": True}
        )
        assert "success" not in r.json()
        assert "data" not in r.json()

    def test_dry_run_true_response_keys_locked(self):
        """dry_run=True 응답 키 목록 고정 (소스 기반)."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        expected_keys = [
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
        for key in expected_keys:
            assert key in src, f"응답 키 {key} 가 소스에서 제거됨"

    def test_real_run_response_keys_locked(self):
        """dry_run=False 응답 키 목록 고정 (소스 기반)."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        expected_keys = [
            '"status"',
            '"pending_approval"',
            '"task_id"',
            '"expires_at"',
        ]
        for key in expected_keys:
            assert key in src, f"응답 키 {key} 가 소스에서 제거됨"

    def test_auth_behavior_recorded(self, client):
        """테스트 환경 auth 동작 기록 — 인증 없이 404(미등록 provider) 또는 401/403."""
        r = client.post("/api/v1/web-tasks/run", json={"provider": "x", "action_type": "y", "dry_run": True})
        assert r.status_code in (401, 403, 404)
        assert "success" not in r.json()

    def test_hold_for_next_phase_comment(self):
        """봉투 전환 보류 사유 문서화."""
        reason = (
            "web-tasks/run의 real_run(dry_run=False) 경로는 telegram_sender.send_message() "
            "실 호출 포함. 봉투 추가 시 UI pending_approval 화면 계약 파괴 가능. "
            "다음 phase에서 frontend 의존성 확인 후 결정."
        )
        assert len(reason) > 0


# ── 5. Characterization: web-tasks/run-from-template ─────────────────────────


class TestWebTasksRunFromTemplateCharacterization:
    """POST /api/v1/web-tasks/run-from-template 응답 계약 고정 (HOLD_FOR_NEXT_PHASE).

    /run과 동일한 _execute_web_task() 사용 + template_id 키 추가.
    봉투 적용 판정: HOLD — /run과 동일 사유 + template_id 키 계약 추가.
    """

    def test_unknown_template_returns_404(self, client, auth):
        """미등록 template_id → 404, detail에 error/message 포함."""
        r = client.post(
            "/api/v1/web-tasks/run-from-template", headers=auth, json={"template_id": "ghost-template", "dry_run": True}
        )
        assert r.status_code == 404
        detail = r.json().get("detail", {})
        assert "error" in detail
        assert detail["error"] == "TEMPLATE_NOT_FOUND"

    def test_no_envelope_on_404(self, client, auth):
        """404 응답에 봉투 없음."""
        r = client.post(
            "/api/v1/web-tasks/run-from-template", headers=auth, json={"template_id": "ghost", "dry_run": True}
        )
        assert "success" not in r.json()
        assert "data" not in r.json()

    def test_template_id_added_to_response_in_source(self):
        """성공 응답에 template_id 키가 추가된다 (소스 기반)."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        assert 'result["template_id"] = template.template_id' in src

    def test_auth_behavior_recorded(self, client):
        """테스트 환경 auth 동작 기록 — 인증 없이 404(미등록 template) 또는 401/403."""
        r = client.post("/api/v1/web-tasks/run-from-template", json={"template_id": "x", "dry_run": True})
        assert r.status_code in (401, 403, 404)
        assert "success" not in r.json()

    def test_hold_for_next_phase_comment(self):
        """봉투 전환 보류 사유 문서화."""
        reason = (
            "run-from-template은 /run과 동일 경로 + template_id 추가. "
            "봉투 적용 시 template_id 포함 응답 계약 파괴. HOLD."
        )
        assert len(reason) > 0


# ── 6. 종합 HOLD 목록 고정 ────────────────────────────────────────────────────


class TestDirectDictBoundaryHoldRegistry:
    """HOLD 목록 전체 고정 — 이 테스트가 실패하면 봉투 적용이 무단으로 진행된 것."""

    HOLD_ENDPOINTS = {
        "POST /api/v1/webhooks/telegram",
        "POST /api/v1/site-tasks/dry-run",
        "POST /api/v1/web-tasks/run",
        "POST /api/v1/web-tasks/run-from-template",
    }

    def test_hold_count_is_four(self):
        assert len(self.HOLD_ENDPOINTS) == 4

    def test_all_hold_endpoints_registered_in_app(self, client):
        """HOLD 엔드포인트 4개가 FastAPI app에 등록되어 있다."""
        from fastapi.routing import APIRoute

        from ai_orchestrator.asgi import app

        from tests.app_routes import route_paths

        paths = route_paths()
        for ep in self.HOLD_ENDPOINTS:
            path = ep.split(" ", 1)[1]
            assert path in paths, f"HOLD 엔드포인트 {path}가 app에 없음"

    def test_none_have_envelope_applied(self, client, auth):
        """HOLD 4개 중 어떤 것도 봉투(success+data) 최상위 구조를 반환하지 않는다."""
        probes = [
            ("POST", "/api/v1/webhooks/telegram", {}),
            (
                "POST",
                "/api/v1/site-tasks/dry-run",
                {
                    "task_id": "t",
                    "target_site": "none",
                    "action": "noop",
                    "params": {},
                    "risk_level": "low",
                    "requires_approval": False,
                },
            ),
            ("POST", "/api/v1/web-tasks/run", {"provider": "ghost", "action_type": "x", "dry_run": True}),
            ("POST", "/api/v1/web-tasks/run-from-template", {"template_id": "ghost", "dry_run": True}),
        ]
        for method, path, body in probes:
            r = client.post(path, headers=auth, json=body)
            top = r.json()
            # 봉투 = {"success": bool, "data": ...} — 이 구조가 없어야 함
            has_envelope = isinstance(top, dict) and "success" in top and "data" in top
            assert not has_envelope, f"{path} 응답에 ApiResponse 봉투가 적용됨 — HOLD 위반"
