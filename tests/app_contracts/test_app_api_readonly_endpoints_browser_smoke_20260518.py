"""Tests: APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_01 (2026-05-18)

Priority 1 read-only endpoint 3개 smoke 검증.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_FORBIDDEN_FIELDS = [
    "raw_token",
    "access_token",
    "refresh_token",
    "cookie_value",
    "session_secret",
    "password",
    "approval_token_raw",
    "private_key",
    "certificate_password",
    "secret_value",
    "execute_url",
    "deploy_url",
    "restart_url",
]


# ── import 가능 여부 ──────────────────────────────────────────────────────────


def test_smoke_script_import():
    import tools.audits.app.smoke_app_api_readonly_endpoints  # noqa


def test_audit_script_import():
    import tools.audits.app.audit_app_api_readonly_endpoints_browser_smoke  # noqa


# ── smoke 메타 ────────────────────────────────────────────────────────────────


def test_smoke_endpoint_list():
    from tools.audits.app.smoke_app_api_readonly_endpoints import ENDPOINTS

    assert len(ENDPOINTS) == 3


def test_smoke_health_summary_in_endpoints():
    from tools.audits.app.smoke_app_api_readonly_endpoints import ENDPOINTS

    assert "/api/v1/app/health/summary" in ENDPOINTS


def test_smoke_providers_in_endpoints():
    from tools.audits.app.smoke_app_api_readonly_endpoints import ENDPOINTS

    assert "/api/v1/app/providers" in ENDPOINTS


def test_smoke_storage_in_endpoints():
    from tools.audits.app.smoke_app_api_readonly_endpoints import ENDPOINTS

    assert "/api/v1/app/storage/status" in ENDPOINTS


def test_smoke_id():
    from tools.audits.app.smoke_app_api_readonly_endpoints import SMOKE_ID

    assert SMOKE_ID == "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE"


def test_smoke_phase():
    from tools.audits.app.smoke_app_api_readonly_endpoints import SMOKE_PHASE

    assert SMOKE_PHASE == "APP_API_READONLY_ENDPOINTS_BROWSER_SMOKE_01"


# ── smoke 실행 결과 ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def smoke_report():
    from tools.audits.app.smoke_app_api_readonly_endpoints import run_smoke

    return run_smoke()


def test_endpoint_count(smoke_report):
    assert smoke_report.endpoint_count == 3


def test_mutation_request_count_zero(smoke_report):
    assert smoke_report.mutation_request_count == 0


def test_external_http_call_count_zero(smoke_report):
    assert smoke_report.external_http_call_count == 0


def test_db_write_count_zero(smoke_report):
    assert smoke_report.db_write_count == 0


def test_secret_output_count_zero(smoke_report):
    assert smoke_report.secret_output_count == 0


def test_redaction_violations_zero(smoke_report):
    assert smoke_report.redaction_violations == 0


# ── health endpoint 검증 ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def health_result(smoke_report):
    return next(r for r in smoke_report.results if "health" in r.path)


def test_health_http_200(health_result):
    assert health_result.status_code == 200


def test_health_schema_ok(health_result):
    assert health_result.schema_ok, health_result.errors


def test_health_post_tasks_dry_run_enabled(health_result):
    from ai_orchestrator.routers.app_status_router import get_health_summary

    result = get_health_summary()
    assert result["data"]["post_tasks_dry_run_enabled"] is True


def test_health_mutation_not_allowed(health_result):
    assert health_result.mutation_allowed_ok


def test_health_read_only(health_result):
    assert health_result.read_only_ok


# ── providers endpoint 검증 ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def providers_result(smoke_report):
    return next(r for r in smoke_report.results if "providers" in r.path)


def test_providers_http_200(providers_result):
    assert providers_result.status_code == 200


def test_providers_schema_ok(providers_result):
    assert providers_result.schema_ok, providers_result.errors


def test_providers_count_12():
    from ai_orchestrator.routers.app_status_router import get_providers

    result = get_providers()
    assert result["meta"]["provider_count"] == 12


def test_providers_cookie_storage_all_false():
    from ai_orchestrator.routers.app_status_router import get_providers

    for p in get_providers()["data"]["providers"]:
        assert p["cookie_storage_allowed"] is False


def test_providers_token_storage_all_false():
    from ai_orchestrator.routers.app_status_router import get_providers

    for p in get_providers()["data"]["providers"]:
        assert p["token_storage_allowed"] is False


def test_providers_read_only(providers_result):
    assert providers_result.read_only_ok


# ── storage endpoint 검증 ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def storage_result(smoke_report):
    return next(r for r in smoke_report.results if "storage" in r.path)


def test_storage_http_200(storage_result):
    assert storage_result.status_code == 200


def test_storage_named_volume_policy():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    assert "named_volume_status" in get_storage_status()["data"]


def test_storage_app_logs_bind_mount_policy():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    assert "app_logs_bind_mount_status" in get_storage_status()["data"]


def test_storage_approval_token_policy():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    assert "approval_token_policy" in get_storage_status()["data"]


# ── redaction 금지 ────────────────────────────────────────────────────────────


def _check_no_forbidden(data: dict, label: str):
    serialized = json.dumps(data)
    for key in _FORBIDDEN_FIELDS:
        assert f'"{key}"' not in serialized, f"{label}에 금지 필드 '{key}' 발견"


def test_health_no_forbidden_fields():
    from ai_orchestrator.routers.app_status_router import get_health_summary

    _check_no_forbidden(get_health_summary(), "health_summary")


def test_providers_no_forbidden_fields():
    from ai_orchestrator.routers.app_status_router import get_providers

    _check_no_forbidden(get_providers(), "providers")


def test_storage_no_forbidden_fields():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    _check_no_forbidden(get_storage_status(), "storage_status")


# ── POST/approve/reject/execute 없음 ─────────────────────────────────────────


def test_no_post_route_in_status_router():
    from ai_orchestrator.routers.app_status_router import app_status_router

    for r in app_status_router.routes:
        assert "POST" not in list(r.methods), f"POST route 발견: {r.path}"


def test_no_approve_reject_execute_in_status_router():
    from ai_orchestrator.routers import app_status_router as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    for forbidden in ("approve_token", "reject_token", "execute("):
        assert forbidden not in src, f"금지 함수 발견: {forbidden}"


# ── 충돌 없음 ─────────────────────────────────────────────────────────────────


def test_no_conflict_with_implementation():
    import tests.app_contracts.test_app_api_readonly_endpoints_implementation_20260518  # noqa


def test_no_conflict_with_plan():
    import tests.app_contracts.test_app_api_readonly_endpoints_implementation_plan_20260518  # noqa


def test_no_conflict_with_prep():
    import tests.app_contracts.test_app_api_contract_endpoints_prep_20260518  # noqa


# ── audit verdict ─────────────────────────────────────────────────────────────


def test_audit_verdict():
    from tools.audits.app.audit_app_api_readonly_endpoints_browser_smoke import print_report, run_audit

    run_audit()
    verdict = print_report()
    assert "BLOCKED" not in verdict, f"audit BLOCKED: {verdict}"
