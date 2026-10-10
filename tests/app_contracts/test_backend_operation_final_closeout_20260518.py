"""
Backend Operation Final Closeout 테스트
tests/test_backend_operation_final_closeout_20260518.py

ASSISTANT_BACKEND_OPERATION_FINAL_CLOSEOUT_01

Phase 1 준공 기준선 검증 전용.
router.py 수정 / docker-compose 수정 / 서버 반영 / 컨테이너 재시작 전면 금지.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_module(name, rel_path):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_closeout",
        "tools/audits/backend/audit_backend_operation_final_closeout.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/routers/registry.py").read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def dc_content():
    return (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def gate(audit_mod):
    return audit_mod.POST_TASKS_GATE_STATUS


@pytest.fixture(scope="module")
def storage(audit_mod):
    return audit_mod.STORAGE_PERSISTENCE_STATUS


@pytest.fixture(scope="module")
def legacy(audit_mod):
    return audit_mod.LEGACY_5050_STATUS


@pytest.fixture(scope="module")
def blockers(audit_mod):
    return audit_mod.POST_TASKS_REMAINING_BLOCKERS


@pytest.fixture(scope="module")
def app_conditions(audit_mod):
    return audit_mod.APP_FOUNDATION_CONDITIONS


@pytest.fixture(scope="module")
def deploy_baseline(audit_mod):
    return audit_mod.DEPLOYMENT_BASELINE


# ── 1~3. import / 안전 플래그 ────────────────────────────────────────────────

def test_01_audit_importable(audit_mod):
    assert audit_mod is not None


def test_02_audit_id_correct(audit_mod):
    assert audit_mod.AUDIT_ID == "BACKEND_OPERATION_FINAL_CLOSEOUT"


def test_03_closeout_only_true(audit_mod):
    assert audit_mod.CLOSEOUT_ONLY is True


def test_04_router_modify_forbidden(audit_mod):
    assert audit_mod.ROUTER_MODIFY_ALLOWED is False


def test_05_docker_compose_modify_forbidden(audit_mod):
    assert audit_mod.DOCKER_COMPOSE_MODIFY_ALLOWED is False


def test_06_server_apply_forbidden(audit_mod):
    assert audit_mod.SERVER_APPLY_ALLOWED is False


def test_07_container_restart_forbidden(audit_mod):
    assert audit_mod.CONTAINER_RESTART_ALLOWED is False


# ── 8~15. router.py Phase 1-R 기준선 ─────────────────────────────────────────

def test_08_dry_run_flag_true(router_content):
    assert "POST_TASKS_DRY_RUN_ENABLED = True" in router_content


def test_09_phase_1r_touch(router_content):
    assert (
        'LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"' in router_content
        or "LEGACY_5050_ROUTER_TOUCH_PHASE = 'PHASE_1R'" in router_content
    )


def test_10_task_approve_wiring_false(router_content):
    assert "LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content


def test_11_task_reject_wiring_false(router_content):
    assert "LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content


def test_12_approve_guard_active(router_content):
    assert (
        '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in router_content
        or "_legacy_5050_should_use_route_wiring('TASK_APPROVE')" in router_content
    )


def test_13_execute_task_not_imported_in_router(router_content):
    assert len(router_content.splitlines()) > 100, "router.py 내용이 비어 있거나 너무 짧음 — 아래 assert 가 공허하게 통과한다"
    import_lines = [
        l for l in router_content.splitlines()
        if l.strip().startswith(("import", "from")) and "execute_task" in l
    ]
    assert len(import_lines) == 0, f"execute_task import 발견: {import_lines}"


def test_14_dry_run_branch_present(router_content):
    assert "POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval" in router_content


def test_15_dry_run_log_event_present(router_content):
    assert "DRY_RUN_GATE_BLOCKED" in router_content


# ── 16~19. docker-compose storage 기준선 ─────────────────────────────────────

def test_16_storage_named_volume_present(dc_content):
    assert "api_storage:/app/ai_orchestrator/storage" in dc_content


def test_17_app_logs_bind_mount_present(dc_content):
    assert "data/app-logs:/app/logs" in dc_content


def test_18_secrets_bind_ro_present(dc_content):
    assert "./secrets/api:/run/secrets/api:ro" in dc_content


def test_19_log_dir_env_set(dc_content):
    assert "LOG_DIR: /app/ai_orchestrator/storage" in dc_content


# ── 20~22. storage persistence matrix ────────────────────────────────────────

def test_20_storage_named_volume_persisted(storage):
    assert storage["storage_named_volume"]["persisted"] is True


def test_21_app_logs_bind_persisted(storage):
    assert storage["app_logs_bind_mount"]["persisted"] is True


def test_22_all_critical_paths_persisted(storage):
    assert storage["all_critical_paths_persisted"] is True


# ── 23~27. POST /tasks gate 상태 ─────────────────────────────────────────────

def test_23_dry_run_flag_active(gate):
    assert gate["value"] is True


def test_24_runtime_smoke_verified(gate):
    assert gate["runtime_verified"] is True


def test_25_smoke_approval_token_null(gate):
    assert gate["smoke_result"]["approval_token_id"] is None


def test_26_smoke_dry_run_true(gate):
    assert gate["smoke_result"]["dry_run"] is True


def test_27_approve_execute_not_connected(gate):
    assert gate["approve_execute_not_connected"] is True


# ── 28~30. Legacy 5050 상태 ──────────────────────────────────────────────────

def test_28_legacy_router_disabled(legacy):
    assert legacy["router_enabled"] is False


def test_29_legacy_guards_active(legacy):
    assert legacy["guards_active"] is True


def test_30_legacy_wiring_all_disabled(legacy):
    assert legacy["task_approve_wiring"] is False
    assert legacy["task_reject_wiring"] is False
    assert legacy["inbox_email_fetch_wiring"] is False


# ── 31~33. 남은 blockers ─────────────────────────────────────────────────────

def test_31_post_tasks_blockers_exist(blockers):
    assert len(blockers["blockers"]) >= 2


def test_32_dry_run_disable_requires_approval(blockers):
    b2 = next((b for b in blockers["blockers"] if b["id"] == "B-2"), None)
    assert b2 is not None
    assert "승인" in b2["required_before_disable"]


def test_33_enable_condition_requires_approval(blockers):
    assert "승인" in blockers["enable_condition"]


# ── 34~37. 앱 착공 조건 ──────────────────────────────────────────────────────

def test_34_app_can_start_true(app_conditions):
    assert app_conditions["app_can_start"] is True


def test_35_backend_ready_true(app_conditions):
    assert app_conditions["backend_ready"] is True


def test_36_conditions_met_gte_5(app_conditions):
    assert len(app_conditions["conditions_met"]) >= 5


def test_37_next_phase_defined(app_conditions):
    assert app_conditions["phase"] == "APP_FOUNDATION_MVP_PREP_01"


# ── 38~40. 배포 SOP ──────────────────────────────────────────────────────────

def test_38_deploy_sop_steps_gte_5(deploy_baseline):
    assert len(deploy_baseline["deploy_sop"]["steps"]) >= 5


def test_39_deploy_sop_has_build_step(deploy_baseline):
    steps = deploy_baseline["deploy_sop"]["steps"]
    assert any("build" in s.lower() for s in steps)


def test_40_deploy_sop_warning_no_restart(deploy_baseline):
    warning = deploy_baseline["deploy_sop"]["warning"]
    assert "restart" in warning.lower() or "재시작" in warning


# ── 41~45. audit verdict ─────────────────────────────────────────────────────

def test_41_completed_phases_gte_10(audit_result):
    assert audit_result["completed_phases_count"] >= 10


def test_42_all_phases_pass(audit_result):
    assert audit_result["all_phases_pass"] is True


def test_43_dry_run_gate_confirmed(audit_result):
    assert audit_result["dry_run_gate_active"] is True
    assert audit_result["dry_run_gate_runtime_verified"] is True


def test_44_storage_persisted(audit_result):
    assert audit_result["storage_all_persisted"] is True


def test_45_verdict_acceptable(audit_result):
    assert audit_result["verdict"] in (
        "BACKEND_PHASE1_CLOSEOUT_READY",
        "BACKEND_PHASE1_CLOSEOUT_READY_WITH_WARN",
    ), f"verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_46_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_47_external_site_registry_files_present(audit_result):
    assert audit_result["external_site_registry"]["audit_script_exists"] is True
    assert audit_result["external_site_registry"]["test_file_exists"] is True
