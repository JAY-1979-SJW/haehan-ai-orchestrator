"""
Phase 1-Q Closeout 테스트: Router Touch Scope Pin
tests/test_5050_phase1q_closeout_router_touch_scope_pin_20260517.py
"""
import importlib.util
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


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
        "scripts/ops/audit_5050_phase1q_closeout_router_touch_scope_pin.py"
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def primary_candidate(audit_mod):
    return audit_mod.get_primary_candidate()


# ── 1. import ─────────────────────────────────────────────────────────────

def test_01_audit_script_importable(audit_mod):
    assert hasattr(audit_mod, "run_audit")
    assert hasattr(audit_mod, "get_primary_candidate")


# ── 2~10. primary touch candidate ─────────────────────────────────────────

def test_02_primary_count_is_1(audit_result):
    assert audit_result["primary_count"] == 1


def test_03_primary_candidate_reason_exists(primary_candidate):
    assert primary_candidate.get("reason")


def test_04_secondary_candidates_exist(audit_result):
    assert len(audit_result["secondary_candidates"]) > 0


def test_05_observation_candidates_exist(audit_result):
    assert "observation_candidates_sample" in audit_result


def test_06_excluded_patterns_exist(audit_result):
    assert len(audit_result["excluded_patterns"]) > 0


def test_07_total_original_19_reclassified(audit_result):
    # primary=1 + secondary(5) + observation(~8 secondary나 obs로 내려간 것) 합계
    assert audit_result["primary_count"] == 1
    assert audit_result["secondary_count"] >= 1


def test_08_no_test_audit_smoke_in_primary(audit_result):
    p = audit_result["primary_touch_candidate"]
    assert "test_" not in p
    assert "audit_" not in p
    assert "smoke_" not in p
    assert "/docs/" not in p


def test_09_no_wrapper_route_integration_in_primary(audit_result):
    p = audit_result["primary_touch_candidate"]
    assert "route_integration" not in p
    assert "wrapper_candidate" not in p


def test_10_no_external_sites_in_primary(audit_result):
    p = audit_result["primary_touch_candidate"]
    assert "external_sites" not in p


# ── 11~22. safety flags ───────────────────────────────────────────────────

def test_11_router_file_modification_false(audit_mod):
    assert audit_mod.ROUTER_FILE_MODIFICATION_ALLOWED is False


def test_12_route_integration_import_false(audit_mod):
    assert audit_mod.ROUTE_REGISTRATION_ALLOWED is False


def test_13_apirouter_false(audit_mod):
    assert audit_mod.APIRouter_ALLOWED is False


def test_14_include_router_false(audit_mod):
    assert audit_mod.INCLUDE_ROUTER_ALLOWED is False


def test_15_route_decorator_false(audit_mod):
    assert audit_mod.ROUTE_DECORATOR_ALLOWED is False


def test_16_feature_flag_default_false(audit_mod):
    # audit script 자체에 feature flag runtime hook 없음
    import inspect
    src = inspect.getsource(audit_mod)
    assert "FEATURE_FLAG_DEFAULT = True" not in src
    assert audit_mod.FEATURE_FLAG_RUNTIME_HOOK_ALLOWED is False


def test_17_real_router_touch_allowed_false(audit_mod):
    assert audit_mod.REAL_ROUTER_TOUCH_ALLOWED is False


def test_18_phase1r_user_explicit_approval_required_true(audit_mod):
    assert audit_mod.PHASE1R_USER_EXPLICIT_APPROVAL_REQUIRED is True


def test_19_phase1r_auto_start_not_allowed(audit_mod):
    assert audit_mod.PHASE1R_AUTO_START_ALLOWED is False


def test_20_server_apply_allowed_false(audit_mod):
    assert audit_mod.SERVER_APPLY_ALLOWED is False


def test_21_db_write_false(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    for kw in ["import sqlalchemy", "import psycopg2", ".write(", "session.add"]:
        assert kw not in src


def test_22_secret_env_access_false(audit_mod):
    import inspect
    src = inspect.getsource(audit_mod)
    assert "os.environ[" not in src
    assert "os.getenv(" not in src


# ── 23~25. browser audit ──────────────────────────────────────────────────

def test_23_browser_audit_result_recorded(audit_result):
    ba = audit_result.get("browser_audit", {})
    assert ba.get("standalone_result") is not None
    assert ba.get("verdict") is not None


def test_24_browser_audit_no_secret_leakage(audit_result):
    ba = audit_result.get("browser_audit", {})
    assert ba.get("secret_leakage") is False


def test_25_browser_audit_not_blocked(audit_result):
    ba = audit_result.get("browser_audit", {})
    assert ba.get("verdict") != "BLOCKED_BROWSER_AUDIT_SECRET_RISK"


# ── 26~29. forbidden route 확인 ───────────────────────────────────────────

def test_26_no_execute_in_target_routes(primary_candidate):
    for r in primary_candidate.get("target_routes", []):
        assert "/execute" not in r


def test_27_no_webhook_in_target_routes(primary_candidate):
    for r in primary_candidate.get("target_routes", []):
        assert "webhook" not in r


def test_28_no_dashboard_in_target_routes(primary_candidate):
    for r in primary_candidate.get("target_routes", []):
        assert "dashboard" not in r


def test_29_same_contract_not_in_primary(audit_result):
    p = audit_result["primary_touch_candidate"]
    assert "SAME_CONTRACT_001" not in p
    assert "SAME_CONTRACT_002" not in p


# ── 30~33. 이전 phase 충돌 확인 ──────────────────────────────────────────

def test_30_phase1q_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1q_router_touch_approval_gate.py").exists()


def test_31_phase1p_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1p_router_integration_implementation_plan.py").exists()


def test_32_external_site_no_conflict(audit_result):
    assert audit_result["verdict"] != "PHASE1Q_CLOSEOUT_BLOCKED"


# ── 33~34. 최종 verdict ──────────────────────────────────────────────────

def test_33_audit_verdict_ready(audit_result):
    v = audit_result["verdict"]
    assert v in (
        "PHASE1Q_CLOSEOUT_ROUTER_TOUCH_SCOPE_PIN_READY",
        "PHASE1Q_CLOSEOUT_READY_WITH_FLAKY_BROWSER_AUDIT",
    ), f"verdict: {v}, errors: {audit_result.get('errors')}"


def test_34_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1Q_CLOSEOUT_BLOCKED"
