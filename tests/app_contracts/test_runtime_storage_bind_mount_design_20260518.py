"""
Runtime Storage Bind Mount Design 테스트
tests/test_runtime_storage_bind_mount_design_20260518.py

ASSISTANT_BACKEND_RUNTIME_STORAGE_BIND_MOUNT_DESIGN_01

설계 공정 검증 전용.
docker-compose.yml 수정 / 컨테이너 재시작 / 서버 반영 전면 금지.
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
        "audit_bind_mount_design",
        "tools/audits/backend/audit_runtime_storage_bind_mount_design.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def findings(audit_mod):
    return audit_mod.INVESTIGATION_FINDINGS


@pytest.fixture(scope="module")
def design(audit_mod):
    return audit_mod.BIND_MOUNT_DESIGN


@pytest.fixture(scope="module")
def policy(audit_mod):
    return audit_mod.STORAGE_POLICY_FINAL


@pytest.fixture(scope="module")
def next_phase(audit_mod):
    return audit_mod.NEXT_PHASE_CONDITIONS


@pytest.fixture(scope="module")
def storage_map(audit_mod):
    return audit_mod.CURRENT_STORAGE_MAP


# ── 1~3. import / 안전 플래그 ────────────────────────────────────────────────

def test_01_audit_importable(audit_mod):
    assert audit_mod is not None


def test_02_audit_id_correct(audit_mod):
    assert audit_mod.AUDIT_ID == "RUNTIME_STORAGE_BIND_MOUNT_DESIGN"


def test_03_design_only_true(audit_mod):
    assert audit_mod.DESIGN_ONLY is True


def test_04_docker_compose_modify_forbidden(audit_mod):
    assert audit_mod.DOCKER_COMPOSE_MODIFY_ALLOWED is False


def test_05_container_restart_forbidden(audit_mod):
    assert audit_mod.CONTAINER_RESTART_ALLOWED is False


def test_06_server_apply_forbidden(audit_mod):
    assert audit_mod.SERVER_APPLY_ALLOWED is False


def test_07_secret_output_forbidden(audit_mod):
    assert audit_mod.SECRET_OUTPUT_ALLOWED is False


# ── 8~11. 조사 결론 ───────────────────────────────────────────────────────────

def test_08_log_dir_env_confirmed(findings):
    assert "LOG_DIR_env" in findings
    assert findings["LOG_DIR_env"]["verdict"] == "CORRECTLY_CONFIGURED"


def test_09_storage_named_volume_confirmed(findings):
    assert "storage_named_volume" in findings
    assert findings["storage_named_volume"]["persisted_across_rebuild"] is True


def test_10_app_logs_not_persisted_confirmed(findings):
    assert "app_logs_dir" in findings
    assert findings["app_logs_dir"]["not_bind_mounted"] is True
    assert findings["app_logs_dir"]["persisted_across_rebuild"] is False


def test_11_execution_history_path_confirmed(findings):
    ef = findings.get("execution_history_path", {})
    assert ef.get("persisted_in_named_volume") is True
    assert "storage" in ef.get("env_based_path", "")
    assert ef.get("verdict") == "CORRECTLY_CONFIGURED_NOT_YET_CREATED"


# ── 12~16. 파일별 정책 ────────────────────────────────────────────────────────

def test_12_approval_tokens_ephemeral(policy):
    assert "EPHEMERAL" in policy["approval_tokens"]["classification"]


def test_13_audit_logs_persistent(policy):
    assert policy["audit_logs"]["classification"] == "PERSISTENT_AUDIT_REQUIRED"
    assert policy["audit_logs"]["verdict"] == "CORRECTLY_PERSISTED"


def test_14_execution_history_correctly_configured(policy):
    assert policy["execution_history"]["verdict"] == "CORRECTLY_CONFIGURED"
    assert "named_volume" in policy["execution_history"]["persistence"]


def test_15_orchestrator_log_risk_pending_fix(policy):
    assert "RISK" in policy["orchestrator_log"]["verdict"]
    assert "BIND" in policy["orchestrator_log"]["action"]


def test_16_chrome_ui_monitor_disposable(policy):
    assert policy["chrome_ui_monitor_state"]["verdict"] == "DISPOSABLE_CONFIRMED"


# ── 17~22. 설계안 ─────────────────────────────────────────────────────────────

def test_17_bind_mount_design_exists(design):
    assert design.get("options") and len(design["options"]) >= 2


def test_18_design_status_design_only(design):
    assert design["status"] == "DESIGN_ONLY"


def test_19_recommended_option_selected(design):
    assert design.get("recommended_option") in design["options"]


def test_20_option_a_targets_app_logs(design):
    opt_a = design["options"].get("OPTION_A_BIND_MOUNT", {})
    dc_add = str(opt_a.get("docker_compose_addition", ""))
    assert "logs" in dc_add.lower()


def test_21_implementation_phase_defined(design):
    assert design.get("implementation_phase")


def test_22_approval_required_stated(design):
    assert design.get("approval_required")


# ── 23~26. storage map ────────────────────────────────────────────────────────

def test_23_storage_named_volume_in_map(storage_map):
    assert any("storage" in k for k in storage_map)


def test_24_app_logs_not_persisted_in_map(storage_map):
    logs_entry = storage_map.get("/app/logs/", {})
    assert logs_entry.get("persisted") is False


def test_25_secrets_bind_readonly_in_map(storage_map):
    secrets_entry = storage_map.get("/run/secrets/api/", {})
    assert secrets_entry.get("mount_type") == "bind_readonly"


# ── 27~30. 다음 공정 ─────────────────────────────────────────────────────────

def test_27_next_phase_defined(next_phase):
    assert next_phase.get("phase") == "RUNTIME_STORAGE_BIND_MOUNT_APPLY_01"


def test_28_next_phase_requires_approval(next_phase):
    assert next_phase.get("requires_approval") is True


def test_29_next_phase_conditions_gte_5(next_phase):
    assert len(next_phase.get("conditions", [])) >= 5


def test_30_next_phase_status_pending(next_phase):
    assert "PENDING" in next_phase.get("current_status", "")


# ── 31~35. audit verdict ─────────────────────────────────────────────────────

def test_31_docker_compose_modified_field_exists(audit_result):
    # APPLY 공정 이후 bind mount가 추가된 상태에서도 audit은 PASS여야 함.
    assert "docker_compose_modified" in audit_result


def test_32_container_not_restarted(audit_result):
    assert audit_result["container_restarted"] is False


def test_33_execution_history_persisted_confirmed(audit_result):
    assert audit_result["execution_history_persisted"] is True


def test_34_app_logs_risk_identified(audit_result):
    assert audit_result["app_logs_persistence_risk"] is True


def test_35_verdict_acceptable(audit_result):
    assert audit_result["verdict"] in (
        "RUNTIME_STORAGE_BIND_MOUNT_DESIGN_READY",
        "RUNTIME_STORAGE_BIND_MOUNT_DESIGN_READY_WITH_WARN",
    ), f"verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_36_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"
