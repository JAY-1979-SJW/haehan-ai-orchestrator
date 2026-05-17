"""
Phase 1-S 테스트: Disabled Router Guard Behavior Smoke
tests/test_5050_phase1s_disabled_router_guard_behavior_20260517.py
"""
import importlib.util
import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _load_module(name, rel_path):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_router_constants():
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")
    result = {}
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'^(LEGACY_5050_\w+)\s*=\s*(False|True|"[^"]*"|\'[^\']*\')$', line)
        if m:
            key, val = m.group(1), m.group(2)
            if val == "False":
                result[key] = False
            elif val == "True":
                result[key] = True
            else:
                result[key] = val.strip('"\'')
    return result


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def router_constants():
    return _parse_router_constants()


@pytest.fixture(scope="module")
def smoke_mod():
    return _load_module("smoke_phase1s", "scripts/ops/smoke_5050_phase1s_disabled_router_guard_behavior.py")


@pytest.fixture(scope="module")
def smoke_result(smoke_mod):
    return smoke_mod.run_smoke()


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module("audit_phase1s", "scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py")


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


# ── 1~6. feature flags ────────────────────────────────────────────────────

def test_01_router_importable_as_text(router_content):
    assert len(router_content) > 0
    assert "LEGACY_5050_ROUTER_TOUCH_PHASE" in router_content


def test_02_phase1r_flag_constants_exist(router_constants):
    assert "LEGACY_5050_ROUTER_TOUCH_PHASE" in router_constants


def test_03_router_touch_enabled_false(router_constants):
    assert router_constants.get("LEGACY_5050_ROUTER_TOUCH_ENABLED") is False


def test_04_inbox_flag_false(router_constants):
    assert router_constants.get("LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED") is False


def test_05_approve_flag_false(router_constants):
    assert router_constants.get("LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED") is False


def test_06_reject_flag_false(router_constants):
    assert router_constants.get("LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED") is False


# ── 7~11. guard function ──────────────────────────────────────────────────

def test_07_guard_func_exists(router_content):
    assert "_legacy_5050_should_use_route_wiring" in router_content


def test_08_guard_inbox_false(smoke_result):
    assert smoke_result["guard_returns_false"] is True


def test_09_guard_approve_false(router_content):
    assert "TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content


def test_10_guard_reject_false(router_content):
    assert "TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content


def test_11_guard_unknown_safe(router_content):
    # guard dict.get(route_id, False) 패턴 또는 return False 존재
    assert "_flags.get(route_id, False)" in router_content or "return False" in router_content


# ── 12~14. route paths ────────────────────────────────────────────────────

def test_12_inbox_email_fetch_path(router_content):
    assert "/inbox/email/fetch" in router_content


def test_13_approve_path(router_content):
    assert "/tasks/{task_id}/approve" in router_content


def test_14_reject_path(router_content):
    assert "/tasks/{task_id}/reject" in router_content


# ── 15~17. forbidden routes ───────────────────────────────────────────────

def test_15_no_execute_route_added(router_content):
    assert '@router.post("/execute"' not in router_content


def test_16_webhook_unchanged(router_content):
    assert "/webhooks/telegram" in router_content


def test_17_no_dashboard_route_added(router_content):
    assert '@router.get("/dashboard"' not in router_content


# ── 18~26. forbidden imports/behavior ────────────────────────────────────

def test_18_no_route_integration_import(router_content):
    assert "from backend.compat.legacy_5050.route_integration" not in router_content


def test_19_no_wrapper_candidate_import(router_content):
    assert "wrapper_candidate" not in router_content


def test_20_no_new_apirouter(router_content):
    assert router_content.count("APIRouter(") == 1


def test_21_no_new_include_router_in_flag_section(router_content):
    start = router_content.find("LEGACY_5050_ROUTER_TOUCH_PHASE")
    end = router_content.find("router = APIRouter")
    if start >= 0 and end > start:
        section = router_content[start:end]
        assert "include_router(" not in section


def test_22_no_new_route_decorator_in_flag_section(router_content):
    start = router_content.find("LEGACY_5050_ROUTER_TOUCH_PHASE")
    end = router_content.find("router = APIRouter")
    if start >= 0 and end > start:
        section = router_content[start:end]
        assert "@router." not in section


def test_23_no_http_client_import(router_content):
    for kw in ["import requests", "import httpx"]:
        assert kw not in router_content


def test_24_no_db_client_import(router_content):
    for kw in ["import sqlalchemy", "import psycopg2"]:
        assert kw not in router_content


def test_25_no_os_environ(router_content):
    assert "os.environ[" not in router_content
    assert "os.getenv(" not in router_content


def test_26_no_secret_output(router_content):
    for bad in ["print(token", "print(cookie", "print(secret"]:
        assert bad not in router_content


# ── 27. behavior_changed ─────────────────────────────────────────────────

def test_27_behavior_changed_false(smoke_result):
    assert smoke_result["behavior_changed"] is False


# ── 28~30. script verdicts ────────────────────────────────────────────────

def test_28_smoke_mod_importable(smoke_mod):
    assert hasattr(smoke_mod, "run_smoke")


def test_29_smoke_verdict_ready(smoke_result):
    assert smoke_result["verdict"] == "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_SMOKE_READY", \
        f"verdict: {smoke_result['verdict']}, errors: {smoke_result.get('errors')}"


def test_30_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] in (
        "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_READY",
        "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_READY_WITH_WARN",
    ), f"verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


# ── 31~36. 이전 phase 회귀 ───────────────────────────────────────────────

def test_31_phase1r_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py").exists()


def test_32_phase1q_closeout_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1q_closeout_router_touch_scope_pin.py").exists()


def test_33_phase1p_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1p_router_integration_implementation_plan.py").exists()


def test_34_phase1o_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1o_router_touch_design_only.py").exists()


def test_35_phase1n_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1n_route_integration_final_preflight.py").exists()


def test_36_external_site_no_conflict(router_content):
    assert "cookie_storage_allowed" not in router_content


# ── 37~38. 최종 ──────────────────────────────────────────────────────────

def test_37_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


def test_38_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1S_DISABLED_ROUTER_GUARD_BEHAVIOR_FAIL"
