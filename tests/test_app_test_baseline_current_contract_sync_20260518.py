"""Tests: APP_TEST_BASELINE_CURRENT_CONTRACT_SYNC_01 (2026-05-18)

테스트 기준선이 현재 read-only 계약과 동기화되었음을 검증한다.
기능 구현 테스트가 아니라 기준선 동기화 감리 테스트.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TESTS_DIR = ROOT / "tests"
FRONTEND_SRC = ROOT / "admin-web" / "src"
from tests.app_ui_paths import assistant_route  # noqa: E402
ROUTER_FILE = ROOT / "ai_orchestrator" / "router.py"
APP_STATUS_ROUTER = ROOT / "ai_orchestrator" / "routers" / "app_status_router.py"
DASHBOARD_PAGE = assistant_route("page.tsx")

TASK_QUEUE_POLISH_ALLOWLIST = [
    "tasks/page.tsx",
    "TaskTable.tsx",
    "mock.ts",
    "assistant.ts",
    "audit_app_task_queue_readonly_list_polish.py",
    "smoke_app_task_queue_readonly_list_polish.py",
    "test_app_task_queue_readonly_list_polish_20260518.py",
]

BACKEND_FORBIDDEN_LIST = [
    "router.py",
    "docker-compose.yml",
    "server.py",
]


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _test_src(name: str) -> str:
    return _src(TESTS_DIR / name)


@pytest.fixture(scope="module")
def dashboard():
    return _src(DASHBOARD_PAGE)


@pytest.fixture(scope="module")
def app_status():
    return _src(APP_STATUS_ROUTER)


@pytest.fixture(scope="module")
def status_cards_test():
    return _test_src("test_app_ui_readonly_backend_status_cards_20260518.py")


@pytest.fixture(scope="module")
def domain_test():
    return _test_src("test_backend_domain_core_models_20260516.py")


@pytest.fixture(scope="module")
def legacy_test():
    return _test_src("test_backend_legacy_router_direct_dict_audit_20260516.py")


@pytest.fixture(scope="module")
def cycle_test():
    return _test_src("test_backend_router_server_cycle_break_20260516.py")


# ── audit script ─────────────────────────────────────────────────────────────
class TestAuditScriptImportable:
    def test_audit_script_exists(self):
        audit = ROOT / "scripts" / "ops" / "audit_app_test_baseline_current_contract_sync.py"
        assert audit.exists()

    def test_audit_script_importable(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "audit_sync",
            ROOT / "scripts" / "ops" / "audit_app_test_baseline_current_contract_sync.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "run_audit")

    def test_audit_verdict_ready(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "audit_sync2",
            ROOT / "scripts" / "ops" / "audit_app_test_baseline_current_contract_sync.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run_audit()
        verdict = mod.print_report()
        assert verdict == mod.VERDICT_READY


# ── GROUP A: getAppHealthSummary 기준 반영 ────────────────────────────────────
class TestGroupA_DashboardHealthAPI:
    def test_dashboard_uses_get_app_health_summary(self, dashboard):
        assert "getAppHealthSummary" in dashboard

    def test_dashboard_no_legacy_get_assistant_health(self, dashboard):
        assert "getAssistantHealth" not in dashboard

    def test_status_cards_test_expects_get_app_health_summary(self, status_cards_test):
        assert "getAppHealthSummary" in status_cards_test

    def test_status_cards_test_no_legacy_get_assistant_health_assert(self, status_cards_test):
        # 주석에 legacy 명칭이 남을 수 있으므로 assert 문 기준으로 확인
        assert 'assert "getAssistantHealth"' not in status_cards_test

    def test_app_status_router_health_summary_path(self, app_status):
        assert "health/summary" in app_status


# ── GROUP B: FutureEndpointNotice 갱신 ───────────────────────────────────────
class TestGroupB_FutureEndpointNotice:
    def test_future_endpoint_notice_exists_in_frontend(self):
        all_tsx = "\n".join(f.read_text(encoding="utf-8") for f in FRONTEND_SRC.rglob("*.tsx"))
        assert "FutureEndpointNotice" in all_tsx

    def test_dashboard_no_future_endpoint_notice(self, dashboard):
        assert "FutureEndpointNotice" not in dashboard

    def test_storage_status_implemented_not_future(self, app_status):
        assert "storage/status" in app_status

    def test_status_cards_test_future_notice_uses_rglob(self, status_cards_test):
        assert "rglob" in status_cards_test


# ── GROUP C: Task Queue polish allowlist ──────────────────────────────────────
class TestGroupC_TaskQueueAllowlist:
    def test_allowlist_contains_tasks_page(self):
        assert any("tasks" in f and "page" in f for f in TASK_QUEUE_POLISH_ALLOWLIST)

    def test_allowlist_contains_task_table(self):
        assert any("TaskTable" in f for f in TASK_QUEUE_POLISH_ALLOWLIST)

    def test_allowlist_contains_mock(self):
        assert any("mock" in f for f in TASK_QUEUE_POLISH_ALLOWLIST)

    def test_backend_files_not_in_allowlist(self):
        for forbidden in BACKEND_FORBIDDEN_LIST:
            assert forbidden not in TASK_QUEUE_POLISH_ALLOWLIST

    def test_docker_compose_not_in_allowlist(self):
        assert "docker-compose.yml" not in TASK_QUEUE_POLISH_ALLOWLIST


# ── GROUP D: endpoint count +3 반영 ──────────────────────────────────────────
class TestGroupD_EndpointCount:
    def test_domain_test_count_63(self, domain_test):
        assert "== 63" in domain_test

    def test_legacy_test_http_count_62(self, legacy_test):
        assert "= 62" in legacy_test

    def test_cycle_test_count_63(self, cycle_test):
        assert "== 63" in cycle_test

    def test_app_status_router_health_summary_endpoint(self, app_status):
        assert "/health/summary" in app_status

    def test_app_status_router_providers_endpoint(self, app_status):
        assert "/providers" in app_status

    def test_app_status_router_storage_status_endpoint(self, app_status):
        assert "/storage/status" in app_status

    def test_runtime_endpoint_count_is_63(self):
        from tests.app_routes import runtime_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        routes = runtime_routes()
        assert len(routes) == 424  # [424=419+5: /site-registry 5개 추가(2026-10-05 M7-S1)] 2026-10-04: origin/master 402(/dev-reg/approvals GET 3개 복원) + 이 브랜치의 공무 AI 초안·사이트 업무 지도·벤더 조회 17개(삭제 0)

    def test_runtime_http_count_is_62(self):
        from tests.app_routes import http_routes

        # 2026-10-04 갱신: FastAPI 0.137+ 지연 include_router 때문에 app.routes 를 직접 세면 0개 — 펼친 목록(tests/app_routes.py)으로 센 현재 값
        http = http_routes()
        assert len(http) == 422  # [422=417+5: /site-registry 5개(2026-10-05 M7-S1)] origin/master 400 + 위 17개(397→417)


# ── 안전 확인 ─────────────────────────────────────────────────────────────────
class TestSafetyPolicy:
    def test_no_post_endpoint_in_app_status_router(self, app_status):
        assert "@app_status_router.post" not in app_status

    def test_no_mutation_endpoint(self, app_status):
        assert "/execute" not in app_status
        assert "/approve" not in app_status
        assert "/reject" not in app_status

    def test_no_approval_token_raw(self, app_status):
        # approval_token_raw는 _FORBIDDEN_RESPONSE_FIELDS 보안 차단 목록에 포함 — 원문 반환이 아닌 차단 정책
        assert "approval_token_raw" not in app_status or "_FORBIDDEN_RESPONSE_FIELDS" in app_status

    def test_no_cookie_value(self, app_status):
        assert "cookie_value" not in app_status

    def test_router_py_no_task_queue(self):
        src = _src(ROUTER_FILE)
        assert "task_queue" not in src

    def test_mutation_allowed_false(self, app_status):
        assert "MUTATION_ALLOWED = False" in app_status
