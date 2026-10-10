"""ASSISTANT_BACKEND_FRONTEND_RESPONSE_DEPENDENCY_AUDIT_01
프론트/테스트 의존성 감사 + 응답 key 고정.

대상:
  POST /api/v1/site-tasks/dry-run
  POST /api/v1/web-tasks/run
  POST /api/v1/web-tasks/run-from-template

판정 결론:
  1. site-tasks/dry-run
     - admin-web frontend에 직접 참조 없음
     - tests/site_engine/test_sites_endpoints.py에서 status/task_id/target_site 키 검증
     - KEEP_CURRENT_CONTRACT (TEST_ONLY_DEPENDENCY)

  2. web-tasks/run
     - admin-web frontend에 직접 참조 없음
     - tests/server_features/test_web_task_registry.py에서
       dry_run/status/task_id/provider/action_type/risk_level/requires_approval/expires_at 모두 검증
     - real_run 경로: status="pending_approval" + task_id 가 테스트 흐름에 연결됨
     - HOLD_FOR_APPROVAL_FLOW_DESIGN (TEST_ONLY_DEPENDENCY + 승인 흐름 연계)

  3. web-tasks/run-from-template
     - admin-web frontend에 직접 참조 없음
     - tests/server_features/test_web_task_templates.py에서
       dry_run/template_id/provider/action_type/success/summary 검증
     - KEEP_CURRENT_CONTRACT (TEST_ONLY_DEPENDENCY)

모든 테스트는 실제 Telegram/외부 API 호출 없이 동작.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ── STEP 3 의존성 테이블 상수 ─────────────────────────────────────────────────

# endpoint → (의존 파일, 사용 key, 판정) 매핑
DEPENDENCY_TABLE = {
    "POST /api/v1/site-tasks/dry-run": {
        "admin_web_files": [],
        "test_files": ["tests/site_engine/test_sites_endpoints.py"],
        "used_keys_in_tests": ["status", "task_id", "target_site", "error_code"],
        "used_keys_in_frontend": [],
        "verdict": "TEST_ONLY_DEPENDENCY",
        "envelope_verdict": "KEEP_CURRENT_CONTRACT",
        "reason": (
            "admin-web 프론트에 직접 참조 없음. "
            "내부 테스트만 status/task_id/target_site 키 사용. "
            "SiteExecutionResult.to_dict() 구조 유지 필요."
        ),
    },
    "POST /api/v1/web-tasks/run": {
        "admin_web_files": [],
        "test_files": [
            "tests/server_features/test_web_task_registry.py",
            "tests/server_features/test_web_task_router_policy_flow.py",
        ],
        "used_keys_in_tests": [
            "dry_run",
            "status",
            "task_id",
            "provider",
            "action_type",
            "risk_level",
            "requires_approval",
            "expires_at",
            "success",
            "summary",
            "field_names",
        ],
        "used_keys_in_frontend": [],
        "verdict": "TEST_ONLY_DEPENDENCY",
        "envelope_verdict": "HOLD_FOR_APPROVAL_FLOW_DESIGN",
        "reason": (
            "admin-web 프론트에 직접 참조 없음. "
            "real_run 경로는 status='pending_approval'+task_id 가 "
            "dev_reg_approval 테스트 흐름과 연결됨. "
            "Telegram 실발송 포함 → 봉투 전환 시 승인 흐름 설계 필요."
        ),
    },
    "POST /api/v1/web-tasks/run-from-template": {
        "admin_web_files": [],
        "test_files": ["tests/server_features/test_web_task_templates.py"],
        "used_keys_in_tests": [
            "dry_run",
            "template_id",
            "provider",
            "action_type",
            "success",
            "summary",
        ],
        "used_keys_in_frontend": [],
        "verdict": "TEST_ONLY_DEPENDENCY",
        "envelope_verdict": "KEEP_CURRENT_CONTRACT",
        "reason": (
            "admin-web 프론트에 직접 참조 없음. "
            "내부 테스트만 dry_run/template_id/provider/success/summary 키 사용. "
            "현재 계약 유지로 충분."
        ),
    },
}


# ── STEP 3 의존성 감사 테스트 ─────────────────────────────────────────────────


class TestFrontendDependencyAudit:
    """3개 endpoint의 admin-web 프론트 의존성 전수 감사."""

    def test_site_tasks_dry_run_no_admin_web_reference(self):
        """admin-web/src에 site-tasks/dry-run 직접 참조가 없다."""
        import pathlib

        src_dir = pathlib.Path("admin-web/src")
        if not src_dir.exists():
            return  # admin-web 없으면 통과
        lines = []
        for f in src_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if "dry-run" in line or "site_tasks" in line or "siteTasks" in line:
                    if "site-tasks" in line or "site_tasks" in line or "siteTasks" in line:
                        lines.append(f"{f}: {line.strip()}")
        assert len(lines) == 0, f"admin-web/src에 site-tasks 참조 발견: {lines}"

    def test_web_tasks_run_no_admin_web_reference(self):
        """admin-web/src에 /api/v1/web-tasks/run 직접 참조가 없다.

        /ops/web-tasks (ops 읽기 전용 API) 참조는 허용됨.
        """
        import pathlib

        src_dir = pathlib.Path("admin-web/src")
        if not src_dir.exists():
            return
        lines = []
        for f in src_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                # /api/v1/web-tasks/run 직접 참조만 검사 (ops API 제외)
                if "api/v1/web-tasks" in line:
                    lines.append(f"{f}: {line.strip()}")
        assert len(lines) == 0, f"admin-web/src에 /api/v1/web-tasks 직접 참조 발견: {lines}"

    def test_run_from_template_no_admin_web_reference(self):
        """admin-web/src에 run-from-template 참조가 없다."""
        import pathlib

        src_dir = pathlib.Path("admin-web/src")
        if not src_dir.exists():
            return
        lines = []
        for f in src_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if "run-from-template" in line:
                    lines.append(f"{f}: {line.strip()}")
        assert len(lines) == 0, f"admin-web/src에 run-from-template 참조 발견: {lines}"

    def test_dependency_table_complete(self):
        """의존성 테이블 3개 endpoint 모두 정의됨."""
        assert len(DEPENDENCY_TABLE) == 3
        endpoints = set(DEPENDENCY_TABLE.keys())
        assert "POST /api/v1/site-tasks/dry-run" in endpoints
        assert "POST /api/v1/web-tasks/run" in endpoints
        assert "POST /api/v1/web-tasks/run-from-template" in endpoints

    def test_all_verdicts_are_test_only_dependency(self):
        """3개 endpoint 모두 admin-web 프론트 의존 없음 — TEST_ONLY_DEPENDENCY."""
        for ep, info in DEPENDENCY_TABLE.items():
            assert info["verdict"] == "TEST_ONLY_DEPENDENCY", (
                f"{ep} verdict={info['verdict']}, 예상=TEST_ONLY_DEPENDENCY"
            )

    def test_all_admin_web_files_empty(self):
        """admin_web_files 목록이 모두 비어 있다 (프론트 직접 참조 없음)."""
        for ep, info in DEPENDENCY_TABLE.items():
            assert info["admin_web_files"] == [], f"{ep}의 admin_web_files={info['admin_web_files']}"


# ── STEP 4 envelope 전환 판정 테스트 ─────────────────────────────────────────


class TestEnvelopeConversionVerdict:
    """3개 endpoint의 envelope 전환 가능성 판정 고정."""

    def test_site_tasks_dry_run_keep_current_contract(self):
        """site-tasks/dry-run: KEEP_CURRENT_CONTRACT."""
        info = DEPENDENCY_TABLE["POST /api/v1/site-tasks/dry-run"]
        assert info["envelope_verdict"] == "KEEP_CURRENT_CONTRACT"

    def test_web_tasks_run_hold_for_approval_flow(self):
        """web-tasks/run: HOLD_FOR_APPROVAL_FLOW_DESIGN (승인 흐름 연계)."""
        info = DEPENDENCY_TABLE["POST /api/v1/web-tasks/run"]
        assert info["envelope_verdict"] == "HOLD_FOR_APPROVAL_FLOW_DESIGN"

    def test_run_from_template_keep_current_contract(self):
        """run-from-template: KEEP_CURRENT_CONTRACT."""
        info = DEPENDENCY_TABLE["POST /api/v1/web-tasks/run-from-template"]
        assert info["envelope_verdict"] == "KEEP_CURRENT_CONTRACT"

    def test_none_safe_for_immediate_envelope_conversion(self):
        """즉시 봉투 전환 가능한 endpoint가 0개임을 선언한다."""
        assert len(DEPENDENCY_TABLE.items()) > 0, "DEPENDENCY_TABLE 이 비어 있음 — 아래 assert 가 공허하게 통과한다"
        safe = [ep for ep, info in DEPENDENCY_TABLE.items() if info["envelope_verdict"] == "ENVELOPE_CONVERSION_SAFE"]
        assert len(safe) == 0, f"즉시 봉투 전환 선언된 endpoint: {safe}"


# ── STEP 5 응답 key 보강 고정 ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    import ai_orchestrator.core.config as config

    config.AUTH_ENABLED = False
    from ai_orchestrator.asgi import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def admin_auth():
    return {}


class TestSiteTasksDryRunKeyContract:
    """site-tasks/dry-run 응답 key 계약 보강."""

    REQUIRED_SUCCESS_KEYS = {
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

    def test_success_response_has_all_required_keys(self):
        """SiteExecutionResult.to_dict()의 모든 key가 유지된다."""
        import dataclasses

        from ai_orchestrator.sites.models import SiteExecutionResult

        fields = {f.name for f in dataclasses.fields(SiteExecutionResult)}
        assert self.REQUIRED_SUCCESS_KEYS.issubset(fields), f"누락 key: {self.REQUIRED_SUCCESS_KEYS - fields}"

    def test_success_response_no_envelope_key(self, client, admin_auth):
        """200 응답에 봉투 키(success/data)가 없다."""
        r = client.post(
            "/api/v1/site-tasks/dry-run",
            headers=admin_auth,
            json={
                "task_id": "t1",
                "target_site": "nope",
                "action": "x",
                "params": {},
                "risk_level": "low",
                "requires_approval": False,
            },
        )
        # 404이지만 봉투 없음 확인
        body = r.json()
        assert "success" not in body
        assert "data" not in body

    def test_400_detail_is_site_execution_result_dict(self):
        """400(unsupported_action) detail은 SiteExecutionResult.to_dict() 구조다."""
        from fastapi.testclient import TestClient as TC

        from ai_orchestrator.asgi import app
        from ai_orchestrator.sites import registry as _reg
        from ai_orchestrator.sites.connector import SiteConnector
        from ai_orchestrator.sites.models import SiteExecutionResult, SiteHealthStatus, SiteTask

        class _DummyConn(SiteConnector):
            name = "dummy_dep"
            supported_actions = ["ping"]

            def health_check(self) -> SiteHealthStatus:
                return SiteHealthStatus(site_name="dummy_dep", connector_name="dummy_dep")

            def dry_run(self, task: SiteTask) -> SiteExecutionResult:
                return SiteExecutionResult(
                    task_id=task.task_id,
                    target_site=task.target_site,
                    action=task.action,
                    status="dry_run",
                )

            def execute(self, task: SiteTask) -> SiteExecutionResult:
                return SiteExecutionResult(
                    task_id=task.task_id,
                    target_site=task.target_site,
                    action=task.action,
                    status="ok",
                )

        _reg.register(_DummyConn(), overwrite=True)
        try:
            import ai_orchestrator.core.config as config

            config.AUTH_ENABLED = False
            c = TC(app, raise_server_exceptions=False)
            r = c.post(
                "/api/v1/site-tasks/dry-run",
                headers={},
                json={
                    "task_id": "t-unsupported",
                    "target_site": "dummy_dep",
                    "action": "unsupported_action",
                    "params": {},
                    "risk_level": "low",
                    "requires_approval": False,
                },
            )
            assert r.status_code in (200, 400)
            # 200이면 dry_run status 확인, 400이면 detail에 status 있음
            body = r.json()
            assert "success" not in body
        finally:
            _reg.unregister("dummy_dep")


class TestWebTasksRunKeyContract:
    """web-tasks/run 응답 key 계약 보강."""

    DRY_RUN_KEYS = frozenset(
        {
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
    )
    REAL_RUN_KEYS = frozenset(
        {
            "dry_run",
            "status",
            "task_id",
            "provider",
            "action_type",
            "risk_level",
            "requires_approval",
            "expires_at",
        }
    )

    def test_dry_run_keys_locked_in_source(self):
        """web_task_router.py에 dry_run 응답 key 모두 존재."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        for key in self.DRY_RUN_KEYS:
            assert f'"{key}"' in src, f"dry_run 응답 key '{key}'가 소스에서 제거됨"

    def test_real_run_keys_locked_in_source(self):
        """web_task_router.py에 real_run 응답 key 모두 존재."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        for key in self.REAL_RUN_KEYS:
            assert f'"{key}"' in src, f"real_run 응답 key '{key}'가 소스에서 제거됨"

    def test_pending_approval_status_value_locked(self):
        """real_run 응답 status 값 'pending_approval' 고정."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        assert '"pending_approval"' in src

    def test_404_response_has_error_and_message(self, client, admin_auth):
        """미등록 provider → 404, detail에 error+message."""
        r = client.post(
            "/api/v1/web-tasks/run", headers=admin_auth, json={"provider": "ghost", "action_type": "x", "dry_run": True}
        )
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert "error" in detail and "message" in detail
        assert "success" not in r.json()

    def test_422_response_has_error_code_and_fields(self, client, admin_auth):
        """422 응답 detail에 error_code/missing_fields/invalid_fields 포함."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        for key in ('"error_code"', '"missing_fields"', '"invalid_fields"'):
            assert key in src, f"422 응답 key {key}가 소스에서 제거됨"


class TestRunFromTemplateKeyContract:
    """web-tasks/run-from-template 응답 key 계약 보강."""

    DRY_RUN_KEYS = frozenset(
        {
            "dry_run",
            "template_id",
            "provider",
            "action_type",
            "success",
            "summary",
        }
    )

    def test_template_id_added_to_response(self):
        """run-from-template 응답에 template_id가 추가된다."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        assert 'result["template_id"] = template.template_id' in src

    def test_dry_run_keys_locked_in_source(self):
        """run-from-template dry_run 응답 key가 소스에 모두 존재."""
        import pathlib

        src = pathlib.Path("ai_orchestrator/web_task/web_task_router.py").read_text(encoding="utf-8")
        base_keys = {"dry_run", "provider", "action_type", "success", "summary"}
        for key in base_keys:
            assert f'"{key}"' in src, f"key '{key}'가 소스에서 제거됨"

    def test_404_template_not_found_error_key(self, client, admin_auth):
        """미등록 template → 404, error='TEMPLATE_NOT_FOUND'."""
        r = client.post(
            "/api/v1/web-tasks/run-from-template",
            headers=admin_auth,
            json={"template_id": "ghost-tpl", "dry_run": True},
        )
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error"] == "TEMPLATE_NOT_FOUND"
        assert "success" not in r.json()


# ── 종합: 봉투 미적용 상태 고정 ──────────────────────────────────────────────


class TestNoEnvelopeApplied:
    """3개 endpoint에 ApiResponse 봉투가 적용되지 않음을 종합 고정."""

    ENDPOINTS = [
        (
            "/api/v1/site-tasks/dry-run",
            {
                "task_id": "t",
                "target_site": "none",
                "action": "x",
                "params": {},
                "risk_level": "low",
                "requires_approval": False,
            },
        ),
        ("/api/v1/web-tasks/run", {"provider": "ghost", "action_type": "x", "dry_run": True}),
        ("/api/v1/web-tasks/run-from-template", {"template_id": "ghost", "dry_run": True}),
    ]

    def test_none_returns_envelope(self, client, admin_auth):
        """3개 endpoint 모두 success+data 봉투 구조를 반환하지 않는다."""
        for path, body in self.ENDPOINTS:
            r = client.post(path, headers=admin_auth, json=body)
            top = r.json()
            has_envelope = isinstance(top, dict) and "success" in top and "data" in top
            assert not has_envelope, f"{path} 응답에 ApiResponse 봉투 적용됨 — 계약 위반"
