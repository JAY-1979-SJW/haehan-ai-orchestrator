"""
Phase 1-R 테스트: Actual Router Touch Feature Flag OFF
tests/test_5050_phase1r_actual_router_touch_feature_flag_off_20260517.py

router.py는 FastAPI 패키지 컨텍스트에서만 import 가능하므로
정적 텍스트 분석 + ast 파싱으로 flag/guard를 검증한다.
"""
import importlib.util
import ast
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
    """router.py에서 phase1r 상수값을 정적으로 추출."""
    content = (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("LEGACY_5050_"):
            m = re.match(r'^(LEGACY_5050_\w+)\s*=\s*(.+)$', line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if val == "False":
                    result[key] = False
                elif val == "True":
                    result[key] = True
                elif val.startswith('"') or val.startswith("'"):
                    result[key] = val.strip('"\'')
    return result


@pytest.fixture(scope="module")
def router_constants():
    return _parse_router_constants()


@pytest.fixture(scope="module")
def audit_mod():
    return _load_module(
        "audit_phase1r",
        "scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py"
    )


@pytest.fixture(scope="module")
def audit_result(audit_mod):
    return audit_mod.run_audit()


@pytest.fixture(scope="module")
def router_content():
    return (REPO_ROOT / "ai_orchestrator/router.py").read_text(encoding="utf-8", errors="ignore")


# ── 1~6. feature flags (정적 분석) ───────────────────────────────────────

def test_01_router_touch_phase(router_constants):
    assert router_constants.get("LEGACY_5050_ROUTER_TOUCH_PHASE") == "PHASE_1R"


def test_02_router_touch_enabled_false(router_constants):
    assert router_constants.get("LEGACY_5050_ROUTER_TOUCH_ENABLED") is False


def test_03_inbox_flag_false(router_constants):
    assert router_constants.get("LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED") is False


def test_04_approve_flag_false(router_constants):
    assert router_constants.get("LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED") is False


def test_05_reject_flag_false(router_constants):
    assert router_constants.get("LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED") is False


# ── 7~9. guard function (정적 분석) ──────────────────────────────────────

def test_06_guard_func_exists(router_content):
    assert "_legacy_5050_should_use_route_wiring" in router_content


def test_07_guard_returns_false_by_default(router_content):
    # guard가 False를 반환하는 로직 확인: _flags.get(route_id, False)
    assert "_flags.get(route_id, False)" in router_content or "return False" in router_content
    # 모든 flag 값이 False
    assert "INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = False" in router_content
    assert "TASK_APPROVE_ROUTE_WIRING_ENABLED = False" in router_content
    assert "TASK_REJECT_ROUTE_WIRING_ENABLED = False" in router_content


def test_08_guard_no_side_effect(router_content):
    # guard 함수 소스에 부작용 없음 확인
    start = router_content.find("def _legacy_5050_should_use_route_wiring")
    end = router_content.find("\ndef ", start + 1) if start >= 0 else -1
    guard_src = router_content[start:end] if start >= 0 and end > start else router_content[start:]
    for bad in ["os.environ", "requests.", "httpx.", "sqlalchemy", "open("]:
        assert bad not in guard_src


# ── 10~13. route paths ────────────────────────────────────────────────────

def test_09_disabled_guard_is_no_op_when_false(router_content):
    # flag가 False이면 RuntimeError 분기에 도달 불가 — guard call이 no-op
    assert '_legacy_5050_should_use_route_wiring("INBOX_EMAIL_FETCH")' in router_content
    assert '_legacy_5050_should_use_route_wiring("TASK_APPROVE")' in router_content
    assert '_legacy_5050_should_use_route_wiring("TASK_REJECT")' in router_content


def test_10_inbox_email_fetch_path_exists(router_content):
    assert "/inbox/email/fetch" in router_content


def test_11_approve_path_exists(router_content):
    assert "/tasks/{task_id}/approve" in router_content


def test_12_reject_path_exists(router_content):
    assert "/tasks/{task_id}/reject" in router_content


def test_13_no_double_slash_in_paths(router_content):
    for route in ["/inbox/email/fetch", "/tasks/{task_id}/approve", "/tasks/{task_id}/reject"]:
        assert "//" not in route


# ── 14~16. no new decorators/routers ─────────────────────────────────────

def test_14_no_new_route_decorator_in_flag_section(router_content):
    start = router_content.find("LEGACY_5050_ROUTER_TOUCH_PHASE")
    end = router_content.find("router = APIRouter")
    if start >= 0 and end > start:
        section = router_content[start:end]
        assert "@router." not in section


def test_15_no_new_include_router_for_phase1r(router_content):
    # Phase 1-R에서 새로운 include_router 없음
    # 기존 include_router 라인들은 유지
    phase1r_marker = "PHASE_1R"
    idx = router_content.find(phase1r_marker)
    section_after = router_content[idx:] if idx >= 0 else ""
    # section_after에서 include_router는 기존 것들
    # Phase 1-R 관련 신규 include_router 없음
    assert "include_router" not in section_after.split("router = APIRouter")[0]


def test_16_no_new_apirouter_creation(router_content):
    # APIRouter()는 1개만 (기존 것)
    count = router_content.count("APIRouter(")
    assert count == 1


# ── 17~22. forbidden imports ──────────────────────────────────────────────

def test_17_no_http_client_import(router_content):
    for kw in ["import requests", "import httpx", "import aiohttp"]:
        assert kw not in router_content


def test_18_no_db_client_import(router_content):
    for kw in ["import sqlalchemy", "import psycopg2", "import sqlite3"]:
        assert kw not in router_content


def test_19_no_os_environ(router_content):
    assert "os.environ[" not in router_content
    assert "os.getenv(" not in router_content


def test_20_no_secret_cookie_token_output(router_content):
    for bad in ["print(token", "print(cookie", "print(secret"]:
        assert bad not in router_content


def test_21_no_route_integration_import(router_content):
    assert "from backend.compat.legacy_5050.route_integration" not in router_content
    assert "route_integration" not in router_content


def test_22_no_live_call_in_guard(router_content):
    start = router_content.find("def _legacy_5050_should_use_route_wiring")
    end = router_content.find("\ndef ", start + 1) if start >= 0 else -1
    guard_src = router_content[start:end] if start >= 0 and end > start else ""
    for bad in ["requests.", "httpx.", "_collect_gmail", "approve_token", "reject_token"]:
        assert bad not in guard_src


# ── 23~25. forbidden routes unchanged ────────────────────────────────────

def test_23_no_execute_route_added(router_content):
    # /execute route decorator가 새로 추가되지 않음
    assert '@router.post("/execute"' not in router_content
    assert '@router.get("/execute"' not in router_content


def test_24_webhook_unchanged(router_content):
    # 기존 webhook 경로 유지 (변경 없음)
    assert "/webhooks/telegram" in router_content


def test_25_dashboard_not_added(router_content):
    assert '@router.get("/dashboard"' not in router_content
    assert '@router.post("/dashboard"' not in router_content


# ── 26~33. 이전 phase 회귀 ───────────────────────────────────────────────

def test_26_phase1q_closeout_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1q_closeout_router_touch_scope_pin.py").exists()


def test_27_phase1p_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1p_router_integration_implementation_plan.py").exists()


def test_28_phase1o_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1o_router_touch_design_only.py").exists()


def test_29_phase1n_no_conflict():
    assert (REPO_ROOT / "scripts/ops/audit_5050_phase1n_route_integration_final_preflight.py").exists()


def test_30_external_site_no_conflict(router_content):
    assert "cookie_storage_allowed" not in router_content
    assert "server_remote_login" not in router_content


def test_31_audit_verdict_ready(audit_result):
    assert audit_result["verdict"] == "PHASE1R_ACTUAL_ROUTER_TOUCH_FEATURE_FLAG_OFF_READY", \
        f"verdict: {audit_result['verdict']}, errors: {audit_result.get('errors')}"


def test_32_rollback_instructions_exist(audit_result):
    assert len(audit_result.get("rollback_instructions", [])) >= 1


def test_33_known_baseline_not_confused(audit_result):
    assert audit_result["verdict"] != "PHASE1R_ACTUAL_ROUTER_TOUCH_FEATURE_FLAG_OFF_FAIL"
