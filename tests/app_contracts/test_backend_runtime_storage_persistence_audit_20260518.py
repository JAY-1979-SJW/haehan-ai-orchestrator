"""
Backend Runtime Storage Persistence Audit 테스트
tests/test_backend_runtime_storage_persistence_audit_20260518.py

ASSISTANT_BACKEND_RUNTIME_STORAGE_PERSISTENCE_AUDIT_01

설계·감사·분류 검증 전용.
실제 docker-compose 수정 / volume 변경 / 컨테이너 재시작 /
서버 반영 / secret 원문 출력 전면 금지.
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
        "audit_storage_persistence",
        "tools/audits/backend/audit_backend_runtime_storage_persistence.py",
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def sc(audit_mod):
    return audit_mod.STORAGE_CLASSIFICATION


@pytest.fixture(scope="module")
def mounts(audit_mod):
    return audit_mod.DOCKER_MOUNTS_SUMMARY


@pytest.fixture(scope="module")
def bind_plan(audit_mod):
    return audit_mod.RECOMMENDED_BIND_MOUNT_PLAN


@pytest.fixture(scope="module")
def security(audit_mod):
    return audit_mod.SECURITY_FINDINGS


# ── 1~2. import ──────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert audit_mod is not None


def test_02_run_audit_exists(audit_mod):
    assert hasattr(audit_mod, "run_audit")


# ── 3~9. 운영 안전 플래그 ────────────────────────────────────────────────────

def test_03_audit_id_correct(audit_mod):
    assert audit_mod.AUDIT_ID == "BACKEND_RUNTIME_STORAGE_PERSISTENCE_AUDIT"


def test_04_read_only_audit_true(audit_mod):
    assert audit_mod.READ_ONLY_AUDIT is True


def test_05_server_apply_not_allowed(audit_mod):
    assert audit_mod.SERVER_APPLY_ALLOWED is False


def test_06_docker_modification_not_allowed(audit_mod):
    assert audit_mod.DOCKER_MODIFICATION_ALLOWED is False


def test_07_container_restart_not_allowed(audit_mod):
    assert audit_mod.CONTAINER_RESTART_ALLOWED is False


def test_08_secret_value_output_not_allowed(audit_mod):
    assert audit_mod.SECRET_VALUE_OUTPUT_ALLOWED is False


# ── 9~13. 필수 분류 항목 존재 ────────────────────────────────────────────────

def test_09_approval_tokens_storage_exists(sc):
    assert "approval_tokens_jsonl" in sc


def test_10_execution_history_storage_exists(sc):
    assert "execution_history_jsonl" in sc


def test_11_audit_logs_storage_exists(sc):
    assert "audit_logs_jsonl" in sc


def test_12_evidence_chrome_ui_monitor_exists(sc):
    assert "chrome_ui_monitor_state" in sc


def test_13_runtime_cache_task_states_exists(sc):
    assert "task_states_jsonl" in sc


# ── 14~17. 핵심 분류 정확성 ──────────────────────────────────────────────────

def test_14_approval_token_ephemeral_security_sensitive(sc):
    assert sc["approval_tokens_jsonl"]["current_classification"] == "EPHEMERAL_SECURITY_SENSITIVE"


def test_15_audit_log_persistent_required(sc):
    assert sc["audit_logs_jsonl"]["current_classification"] == "PERSISTENT_AUDIT_REQUIRED"


def test_16_execution_history_persistent_required(sc):
    assert sc["execution_history_jsonl"]["current_classification"] == "PERSISTENT_OPERATION_REQUIRED"


def test_17_chrome_ui_monitor_disposable(sc):
    assert sc["chrome_ui_monitor_state"]["current_classification"] == "RUNTIME_CACHE_DISPOSABLE"


# ── 18~20. docker mount 현황 ─────────────────────────────────────────────────

def test_18_docker_mounts_summary_exists(mounts):
    assert mounts.get("mounts") and len(mounts["mounts"]) >= 1


def test_19_storage_named_volume_present(mounts):
    volume_mounts = [m for m in mounts["mounts"] if m["type"] == "volume"]
    storage_mount = [m for m in volume_mounts if "storage" in m["destination"]]
    assert len(storage_mount) >= 1, "storage named volume mount 없음"
    assert storage_mount[0]["persisted_on_host"] is True


def test_20_logs_not_bind_mounted(mounts):
    not_mounted = mounts.get("not_mounted", [])
    logs_path = [p for p in not_mounted if "logs" in p["path"]]
    assert len(logs_path) >= 1, "/app/logs가 not_mounted 목록에 없음"
    assert logs_path[0]["persisted_on_host"] is False


# ── 21~23. 보안 판정 ─────────────────────────────────────────────────────────

def test_21_no_plaintext_secret_detected(security):
    assert security["plaintext_secret_detected"] is False


def test_22_no_token_value_output(security):
    assert security["token_value_output"] is False


def test_23_no_cookie_value_output(security):
    assert security["cookie_value_output"] is False


# ── 24~25. 후속 bind mount 설계 ──────────────────────────────────────────────

def test_24_bind_mount_plan_exists(bind_plan):
    assert bind_plan.get("recommended_additions") is not None
    assert len(bind_plan["recommended_additions"]) >= 1


def test_25_bind_mount_implementation_forbidden_this_phase(bind_plan):
    assert bind_plan.get("implementation_allowed_this_phase") is False


# ── 26~27. persistence risk 항목 ─────────────────────────────────────────────

def test_26_logs_paths_flagged_as_persistence_risk(sc):
    risk_items = [k for k, v in sc.items() if v.get("verdict") == "PERSISTENCE_RISK"]
    logs_risk = [k for k in risk_items if "logs" in k]
    assert len(logs_risk) >= 1, "/app/logs 계열 파일이 PERSISTENCE_RISK로 분류되지 않음"


def test_27_storage_volume_items_correctly_persisted(sc):
    ok_items = [k for k, v in sc.items() if v.get("verdict") == "CORRECTLY_PERSISTED"]
    assert len(ok_items) >= 2, "CORRECTLY_PERSISTED 항목이 부족함"


# ── 28~29. 금지 조건 소스 확인 ───────────────────────────────────────────────

def test_28_docker_compose_not_modified(audit_result):
    assert audit_result["docker_compose_modified"] is False


def test_29_container_not_restarted(audit_result):
    assert audit_result["container_restarted"] is False


# ── 30~33. audit verdict ─────────────────────────────────────────────────────

def test_30_audit_verdict_acceptable(audit_result):
    assert audit_result["verdict"] in (
        "RUNTIME_STORAGE_PERSISTENCE_AUDIT_READY",
        "RUNTIME_STORAGE_PERSISTENCE_AUDIT_WITH_WARN",
    ), f"unexpected verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_31_audit_no_errors(audit_result):
    assert audit_result.get("errors") == [], f"errors: {audit_result['errors']}"


def test_32_storage_persisted_confirmed(audit_result):
    assert audit_result["docker_mounts"]["storage_persisted"] is True


def test_33_logs_not_persisted_confirmed(audit_result):
    assert audit_result["docker_mounts"]["logs_not_persisted"] is True


# ── 34~35. 후속 공정 정의 ────────────────────────────────────────────────────

def test_34_next_phase_defined(audit_result):
    assert audit_result.get("next_phase")


def test_35_persistence_risk_items_noted(audit_result):
    assert len(audit_result.get("persistence_risks", [])) >= 1
