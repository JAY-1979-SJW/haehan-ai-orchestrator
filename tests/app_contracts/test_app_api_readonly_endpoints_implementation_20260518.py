"""Tests: APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01 (2026-05-18)

Priority 1 read-only endpoint 3개 구현 검증.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ── import 가능 여부 ──────────────────────────────────────────────────────────


def test_app_status_router_import():
    import ai_orchestrator.routers.app_status_router  # noqa


def test_audit_script_import():
    import tools.audits.app.audit_app_api_readonly_endpoints_implementation  # noqa


# ── 공정 상수 ─────────────────────────────────────────────────────────────────


def test_phase_constant():
    from ai_orchestrator.routers.app_status_router import APP_STATUS_ROUTER_PHASE

    assert APP_STATUS_ROUTER_PHASE == "APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01"


def test_read_only_enabled():
    from ai_orchestrator.routers.app_status_router import READ_ONLY_API_ENABLED

    assert READ_ONLY_API_ENABLED is True


def test_mutation_not_allowed():
    from ai_orchestrator.routers.app_status_router import MUTATION_ALLOWED

    assert MUTATION_ALLOWED is False


def test_server_action_not_allowed():
    from ai_orchestrator.routers.app_status_router import SERVER_ACTION_ALLOWED

    assert SERVER_ACTION_ALLOWED is False


def test_secret_output_not_allowed():
    from ai_orchestrator.routers.app_status_router import SECRET_VALUE_OUTPUT_ALLOWED

    assert SECRET_VALUE_OUTPUT_ALLOWED is False


# ── route 정의 확인 ──────────────────────────────────────────────────────────


def _get_route_paths():
    from ai_orchestrator.routers.app_status_router import app_status_router

    return [r.path for r in app_status_router.routes]


def _get_route_methods():
    from ai_orchestrator.routers.app_status_router import app_status_router

    return {r.path: list(r.methods) for r in app_status_router.routes}


def test_health_summary_route_defined():
    paths = _get_route_paths()
    assert any("health/summary" in p for p in paths), f"health/summary 없음: {paths}"


def test_providers_route_defined():
    paths = _get_route_paths()
    assert any("providers" in p for p in paths), f"providers 없음: {paths}"


def test_storage_status_route_defined():
    paths = _get_route_paths()
    assert any("storage/status" in p for p in paths), f"storage/status 없음: {paths}"


def test_no_post_routes():
    methods = _get_route_methods()
    for path, ms in methods.items():
        assert "POST" not in ms, f"POST route 발견: {path}"


def test_no_put_patch_delete_routes():
    methods = _get_route_methods()
    for path, ms in methods.items():
        for forbidden in ("PUT", "PATCH", "DELETE"):
            assert forbidden not in ms, f"{forbidden} route 발견: {path}"


# ── health summary 응답 검증 ─────────────────────────────────────────────────


def test_health_summary_response_schema():
    from ai_orchestrator.routers.app_status_router import get_health_summary

    result = get_health_summary()
    assert result["ok"] is True
    data = result["data"]
    assert "service" in data
    assert "health_status" in data
    assert "generated_at" in data
    meta = result["meta"]
    assert "read_only" in meta


def test_health_summary_post_tasks_dry_run_enabled():
    from ai_orchestrator.routers.app_status_router import get_health_summary

    result = get_health_summary()
    assert result["data"]["post_tasks_dry_run_enabled"] is True


def test_health_summary_mutation_not_allowed():
    from ai_orchestrator.routers.app_status_router import get_health_summary

    result = get_health_summary()
    assert result["meta"]["mutation_allowed"] is False


# ── providers 응답 검증 ───────────────────────────────────────────────────────


def test_providers_count_12():
    from ai_orchestrator.routers.app_status_router import get_providers

    result = get_providers()
    assert result["meta"]["provider_count"] == 12
    assert len(result["data"]["providers"]) == 12


def test_providers_cookie_storage_all_false():
    from ai_orchestrator.routers.app_status_router import get_providers

    result = get_providers()
    for p in result["data"]["providers"]:
        assert p["cookie_storage_allowed"] is False, f"{p['provider_id']} cookie_storage_allowed=True"


def test_providers_token_storage_all_false():
    from ai_orchestrator.routers.app_status_router import get_providers

    result = get_providers()
    for p in result["data"]["providers"]:
        assert p["token_storage_allowed"] is False, f"{p['provider_id']} token_storage_allowed=True"


# ── storage 응답 검증 ─────────────────────────────────────────────────────────


def test_storage_named_volume_status():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    result = get_storage_status()
    assert "named_volume_status" in result["data"]


def test_storage_app_logs_bind_mount_status():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    result = get_storage_status()
    assert "app_logs_bind_mount_status" in result["data"]


def test_storage_approval_token_policy():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    result = get_storage_status()
    assert "approval_token_policy" in result["data"]


def test_storage_no_log_raw_content():
    import json

    from ai_orchestrator.routers.app_status_router import get_storage_status

    result = get_storage_status()
    serialized = json.dumps(result)
    assert "TASK_RECEIVED" not in serialized
    assert "APPROVAL_ISSUED" not in serialized


# ── 보안/레드액션 금지 ─────────────────────────────────────────────────────────

_FORBIDDEN_KEYS = [
    "raw_token",
    "access_token",
    "refresh_token",
    "cookie",
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


def _check_no_forbidden(data: dict, label: str):
    import json

    serialized = json.dumps(data)
    for key in _FORBIDDEN_KEYS:
        assert f'"{key}"' not in serialized, f"{label} 응답에 금지 필드 '{key}' 발견"


def test_health_no_forbidden_fields():
    from ai_orchestrator.routers.app_status_router import get_health_summary

    _check_no_forbidden(get_health_summary(), "health_summary")


def test_providers_no_forbidden_fields():
    from ai_orchestrator.routers.app_status_router import get_providers

    _check_no_forbidden(get_providers(), "providers")


def test_storage_no_forbidden_fields():
    from ai_orchestrator.routers.app_status_router import get_storage_status

    _check_no_forbidden(get_storage_status(), "storage_status")


def test_no_server_restart_field():
    import json

    from ai_orchestrator.routers.app_status_router import get_health_summary

    result = json.dumps(get_health_summary())
    assert "restart_url" not in result
    assert "deploy_url" not in result


def test_no_docker_compose_field():
    import json

    from ai_orchestrator.routers.app_status_router import get_health_summary

    result = json.dumps(get_health_summary())
    assert "docker_compose" not in result


# ── 기존 코드 변경 없음 확인 ─────────────────────────────────────────────────


def test_post_tasks_code_unchanged():
    from ai_orchestrator.routers import registry as router

    assert hasattr(router, "submit_task"), "POST /tasks handler 없음"
    assert router.POST_TASKS_DRY_RUN_ENABLED is True


def test_approve_reject_unchanged():
    from ai_orchestrator.routers import registry as router

    assert hasattr(router, "approve_task")
    assert hasattr(router, "reject_task")


# ── 충돌 없음 확인 ───────────────────────────────────────────────────────────


def test_no_conflict_with_plan():
    import tests.app_contracts.test_app_api_readonly_endpoints_implementation_plan_20260518  # noqa


def test_no_conflict_with_prep():
    import tests.app_contracts.test_app_api_contract_endpoints_prep_20260518  # noqa


# ── live-summary 엔드포인트 (실시간 운영 요약) ───────────────────────────────


def test_live_summary_route_defined():
    paths = _get_route_paths()
    assert any("live-summary" in p for p in paths), f"live-summary 없음: {paths}"


def test_live_summary_response_schema():
    from ai_orchestrator.routers.app_status_router import get_live_summary

    result = get_live_summary()
    assert result["ok"] is True
    data = result["data"]
    for key in (
        "service",
        "health_status",
        "post_tasks_dry_run_enabled",
        "phase1_closeout_status",
        "read_only",
        "mutation_allowed",
        "storage",
        "generated_at",
    ):
        assert key in data, f"누락 필드: {key}"
    assert result["meta"]["read_only"] is True


def test_live_summary_read_only_and_no_mutation():
    from ai_orchestrator.routers.app_status_router import get_live_summary

    result = get_live_summary()
    assert result["data"]["read_only"] is True
    assert result["data"]["mutation_allowed"] is False
    assert result["meta"]["mutation_allowed"] is False
    assert result["meta"]["server_action_allowed"] is False


def test_live_summary_no_secret_fields():
    import json

    from ai_orchestrator.routers.app_status_router import _FORBIDDEN_RESPONSE_FIELDS, get_live_summary

    blob = json.dumps(get_live_summary())
    for field in _FORBIDDEN_RESPONSE_FIELDS:
        assert field not in blob, f"금지 필드 노출: {field}"


# ── deployment-status 엔드포인트 (배포 상태, 실행 없음) ──────────────────────


def test_deployment_status_route_defined():
    paths = _get_route_paths()
    assert any("deployment-status" in p for p in paths), f"deployment-status 없음: {paths}"


def test_deployment_status_response_schema():
    from ai_orchestrator.routers.app_status_router import get_deployment_status

    result = get_deployment_status()
    assert result["ok"] is True
    data = result["data"]
    for key in ("state", "build_required", "sop_steps", "deploy_action_allowed", "generated_at"):
        assert key in data, f"누락 필드: {key}"
    assert isinstance(data["sop_steps"], list)


def test_deployment_status_no_server_action():
    from ai_orchestrator.routers.app_status_router import get_deployment_status

    result = get_deployment_status()
    assert result["data"]["deploy_action_allowed"] is False
    assert result["meta"]["server_action_allowed"] is False
    assert result["meta"]["mutation_allowed"] is False


# ── audit verdict ─────────────────────────────────────────────────────────────


def test_audit_verdict():
    from tools.audits.app.audit_app_api_readonly_endpoints_implementation import print_report, run_audit

    run_audit()
    verdict = print_report()
    assert "BLOCKED" not in verdict, f"audit BLOCKED: {verdict}"
