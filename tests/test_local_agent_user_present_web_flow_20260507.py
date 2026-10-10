"""
로컬 Agent 사용자 직접 인증 흐름 테스트

AI는 민감정보를 입력/저장/전송하지 않는다.
safe_to_execute는 항상 False다.
"""

import json
import pathlib

import pytest

from ai_orchestrator.agent_hub.user_present_flow import (
    DECISION_BLOCK,
    DECISION_READONLY,
    DECISION_REQUIRE_API,
    EXEC_LOC_API,
    EXEC_LOC_BLOCKED,
    EXEC_LOC_LOCAL_AGENT,
    EXEC_LOC_SERVER_READONLY,
    EXEC_LOC_USER_PRESENT,
    build_admin_visible_status,
    build_local_agent_instruction,
    build_user_present_task,
    build_user_visible_status,
    mark_user_cancelled,
    mark_user_confirmed_auth,
    mark_user_present_waiting,
    sanitize_admin_visible_payload,
    sanitize_user_visible_payload,
    validate_user_present_flow_result,
)

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "local_agent_user_present_web_flow_20260507.json"
MODULE_PATH = (
    pathlib.Path(__file__).parent.parent / "ai_orchestrator" / "agent_hub" / "user_present_flow.py"
)

REQUIRED_CASE_FIELDS = [
    "workflow_id",
    "site_category",
    "execution_location",
    "user_present_required",
    "local_agent_required",
    "api_required",
    "browser_automation_allowed",
    "allowed_operations",
    "blocked_operations",
    "sensitive_inputs_blocked",
    "user_prompt_required",
    "user_visible_fields",
    "user_hidden_fields",
    "admin_visible_fields",
    "internal_only_fields",
    "final_verdict",
]

FORBIDDEN_IN_USER_PAYLOAD = [
    "secret",
    "token",
    "cookie",
    "session",
    "audit_raw",
    "internal_policy",
    "cross_tenant_data",
]


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def cases(fixture_data):
    return {c["case_id"]: c for c in fixture_data["cases"]}


# ── 1. fixture JSON 로드 가능 ──────────────────────────────────────────────────


def test_fixture_loads(fixture_data):
    assert "cases" in fixture_data
    assert len(fixture_data["cases"]) >= 20


# ── 2. 모든 케이스 필수 필드 존재 ───────────────────────────────────────────────


def test_all_cases_have_required_fields(fixture_data):
    for case in fixture_data["cases"]:
        for field in REQUIRED_CASE_FIELDS:
            assert field in case, f"케이스 {case.get('case_id')} 에 필드 '{field}' 없음"


# ── 3. 은행 공동인증서 로그인은 USER_PRESENT_REQUIRED ──────────────────────────


def test_bank_certificate_is_user_present_required():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_financial_certificate": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] == EXEC_LOC_USER_PRESENT
    assert task["user_present_required"] is True


# ── 4. 금융인증서는 USER_PRESENT_REQUIRED ────────────────────────────────────


def test_financial_certificate_is_user_present_required():
    payload = {
        "site_category": "bank",
        "requires_certificate": False,
        "requires_financial_certificate": True,
        "requires_password": True,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] == EXEC_LOC_USER_PRESENT
    assert task["user_present_required"] is True


# ── 5. OTP 필요 시 USER_PRESENT_REQUIRED ─────────────────────────────────────


def test_otp_required_is_user_present_required():
    payload = {
        "site_category": "bank",
        "requires_certificate": False,
        "requires_financial_certificate": False,
        "requires_otp": True,
        "requires_password": True,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] == EXEC_LOC_USER_PRESENT


# ── 6. CAPTCHA 필요 시 BLOCK ─────────────────────────────────────────────────


def test_captcha_required_is_blocked():
    payload = {
        "site_category": "government",
        "requires_captcha": True,
        "requires_certificate": False,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_password": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] == EXEC_LOC_BLOCKED
    assert task["local_agent_decision"] == DECISION_BLOCK


# ── 7. password 입력은 AI 입력 BLOCK ─────────────────────────────────────────


def test_password_input_blocked_for_ai():
    payload = {
        "site_category": "bank",
        "requires_password": True,
        "requires_certificate": False,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert "password" in task["sensitive_inputs_blocked"]
    assert task["blocked_for_ai_input"] is True


# ── 8. certificate_password 입력은 AI 입력 BLOCK ─────────────────────────────


def test_certificate_password_blocked_for_ai():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": False,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert "certificate_password" in task["sensitive_inputs_blocked"]
    assert task["blocked_for_ai_input"] is True


# ── 9. Google은 API_REQUIRED ─────────────────────────────────────────────────


def test_google_is_api_required():
    payload = {
        "site_category": "cloud_service",
        "requires_certificate": False,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_password": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "api_required": True,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] == EXEC_LOC_API
    assert task["local_agent_decision"] == DECISION_REQUIRE_API


# ── 10. G2B read-only는 SERVER_BROWSER_READONLY_OK 가능 ────────────────────


def test_g2b_readonly_is_server_ok():
    payload = {
        "site_category": "procurement",
        "requires_certificate": False,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_password": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "api_required": False,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] == EXEC_LOC_SERVER_READONLY
    assert task["local_agent_decision"] == DECISION_READONLY


# ── 11. 홈택스는 USER_PRESENT_REQUIRED 또는 LOCAL_AGENT_REQUIRED ─────────────


def test_hometax_certificate_is_user_present():
    payload = {
        "site_category": "tax",
        "requires_certificate": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_password": True,
        "requires_captcha": False,
        "requires_security_plugin": True,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] in (EXEC_LOC_USER_PRESENT, EXEC_LOC_LOCAL_AGENT)


# ── 12. 4대보험은 LOCAL_AGENT_REQUIRED ───────────────────────────────────────


def test_four_insurance_is_local_agent_required():
    payload = {
        "site_category": "insurance",
        "requires_certificate": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_password": True,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert task["execution_location"] in (EXEC_LOC_LOCAL_AGENT, EXEC_LOC_USER_PRESENT)
    assert task["local_agent_required"] is True


# ── 13. user auth completed 상태 전이 가능 ────────────────────────────────────


def test_user_confirmed_auth_state_transition():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "workflow_run_id": "run_test_001",
    }
    task = build_user_present_task(payload)
    task = mark_user_present_waiting(task)
    assert task["state"] == "WAITING_FOR_USER"
    task = mark_user_confirmed_auth(task)
    assert task["state"] == "USER_CONFIRMED"


# ── 14. user cancelled 상태 전이 가능 ───────────────────────────────────────


def test_user_cancelled_state_transition():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "workflow_run_id": "run_test_002",
    }
    task = build_user_present_task(payload)
    task = mark_user_cancelled(task)
    assert task["state"] == "CANCELLED"


# ── 15. safe_to_execute는 모든 케이스 false ──────────────────────────────────


def test_safe_to_execute_always_false(fixture_data):
    for case in fixture_data["cases"]:
        assert case.get("safe_to_execute") is False, f"safe_to_execute가 False가 아님: {case['case_id']}"


def test_build_task_safe_to_execute_always_false():
    payloads = [
        {
            "site_category": "bank",
            "requires_certificate": True,
            "requires_password": True,
            "requires_financial_certificate": False,
            "requires_otp": False,
            "requires_captcha": False,
            "requires_security_plugin": False,
        },
        {
            "site_category": "procurement",
            "requires_certificate": False,
            "requires_password": False,
            "requires_financial_certificate": False,
            "requires_otp": False,
            "requires_captcha": False,
            "requires_security_plugin": False,
        },
        {
            "site_category": "cloud_service",
            "api_required": True,
            "requires_certificate": False,
            "requires_password": False,
            "requires_financial_certificate": False,
            "requires_otp": False,
            "requires_captcha": False,
            "requires_security_plugin": False,
        },
    ]
    for p in payloads:
        task = build_user_present_task(p)
        assert task["safe_to_execute"] is False


# ── 16. blocked_next_actions에 type/submit 포함 ──────────────────────────────


def test_blocked_next_actions_contain_type_and_submit():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert "type" in task["blocked_next_actions"]
    assert "submit" in task["blocked_next_actions"]


# ── 17. sensitive_inputs_blocked에 password/otp/certificate_password 포함 ───


def test_sensitive_inputs_blocked_fields():
    payload = {
        "site_category": "bank",
        "requires_password": True,
        "requires_otp": True,
        "requires_certificate": True,
        "requires_financial_certificate": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
    }
    task = build_user_present_task(payload)
    assert "password" in task["sensitive_inputs_blocked"]
    assert "otp" in task["sensitive_inputs_blocked"]
    assert "certificate_password" in task["sensitive_inputs_blocked"]


# ── 18. user_visible_payload에 secret/token/cookie/session 없음 ─────────────


def test_user_visible_payload_no_secret_fields():
    dirty = {
        "task_name": "login",
        "site_name_redacted": "example.co.kr",
        "secret": "MY_SECRET",
        "token": "abc123",
        "cookie": "session=xyz",
        "session": "xyz",
    }
    clean = sanitize_user_visible_payload(dirty)
    for key in FORBIDDEN_IN_USER_PAYLOAD:
        assert key not in clean, f"user_visible_payload에 '{key}' 포함됨"


# ── 19. user_visible_payload에 audit_raw 없음 ──────────────────────────────


def test_user_visible_payload_no_audit_raw():
    dirty = {"task_name": "login", "audit_raw": "raw_audit_content"}
    clean = sanitize_user_visible_payload(dirty)
    assert "audit_raw" not in clean


# ── 20. user_visible_payload에 internal_policy 없음 ─────────────────────────


def test_user_visible_payload_no_internal_policy():
    dirty = {"task_name": "login", "internal_policy": "FULL_POLICY_TEXT"}
    clean = sanitize_user_visible_payload(dirty)
    assert "internal_policy" not in clean


# ── 21. user_visible_payload에 cross_tenant_data 없음 ───────────────────────


def test_user_visible_payload_no_cross_tenant_data():
    dirty = {"task_name": "login", "cross_tenant_data": {"tenant_002": "data"}}
    clean = sanitize_user_visible_payload(dirty)
    assert "cross_tenant_data" not in clean


# ── 22. admin_visible_payload에도 raw secret 없음 ────────────────────────────


def test_admin_visible_payload_no_raw_secrets():
    dirty = {
        "workflow_id": "wf_001",
        "tenant_id": "t001",
        "password": "hunter2",
        "token": "tok123",
        "cookie": "session=abc",
        "otp": "123456",
    }
    clean = sanitize_admin_visible_payload(dirty)
    for key in ("password", "token", "cookie", "otp"):
        assert key not in clean, f"admin_visible_payload에 '{key}' 포함됨"
    assert "workflow_id" in clean
    assert "tenant_id" in clean


# ── 23. 사용자 화면은 자기 workflow_run_id만 표시 ───────────────────────────


def test_user_visible_shows_own_workflow_run_id_only():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "workflow_run_id": "run_own_001",
        "other_user_workflow_run_id": "run_other_999",
    }
    status = build_user_visible_status(payload)
    assert status.get("workflow_run_id") == "run_own_001"
    assert "other_user_workflow_run_id" not in status


# ── 24. 다른 user_id/tenant_id 작업은 숨김 ──────────────────────────────────


def test_user_visible_hides_other_tenant_data():
    dirty = {
        "task_name": "login",
        "other_tenant_data": {"tenant_002": "sensitive"},
        "other_user_tasks": [{"user_id": "user_002"}],
    }
    clean = sanitize_user_visible_payload(dirty)
    assert "other_tenant_data" not in clean
    assert "other_user_tasks" not in clean


# ── 25. 쿠키/session/token 추출 코드 없음 ───────────────────────────────────


def test_no_cookie_session_token_extraction_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_patterns = [
        "document.cookie",
        "localStorage.getItem",
        "sessionStorage.getItem",
        "extract_cookie(",
        "extract_session(",
        "get_token()",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, f"소스에 금지 패턴 '{pattern}' 발견"


# ── 26. 인증서 비밀번호 입력 코드 없음 ──────────────────────────────────────


def test_no_certificate_password_input_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["fill_certificate_password(", "type_certificate_password(", "enter_cert_pw("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 금지 패턴 '{pattern}' 발견"


# ── 27. OTP 입력 코드 없음 ──────────────────────────────────────────────────


def test_no_otp_input_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["fill_otp(", "type_otp(", "enter_otp(", "input_otp("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 금지 패턴 '{pattern}' 발견"


# ── 28. playwright fill/type/submit 호출 없음 ────────────────────────────────


def test_no_playwright_fill_type_submit():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [".fill(", ".type(", ".click(submit", "page.submit("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 Playwright 금지 패턴 '{pattern}' 발견"


# ── 29. DB write 코드 없음 ───────────────────────────────────────────────────


def test_no_db_write_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE", ".execute(", "db.commit("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 DB write 패턴 '{pattern}' 발견"


# ── 30. site_access_compatibility_auditor와 호환 ─────────────────────────────


def test_compatible_with_site_access_compatibility_auditor():
    auditor_path = (
        pathlib.Path(__file__).parent.parent
        / "ai_orchestrator"
        / "browser_tool"
        / "policy"
        / "site_access_compatibility_auditor.py"
    )
    assert auditor_path.exists(), "site_access_compatibility_auditor.py 파일 없음"
    # 충돌하는 실행 위치 코드가 없는지 확인
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "SERVER_BROWSER_READONLY_OK" in source
    assert "LOCAL_AGENT_REQUIRED" in source
    assert "USER_PRESENT_REQUIRED" in source


# ── 31. site_compliance_policy와 호환 ────────────────────────────────────────


def test_compatible_with_site_compliance_policy():
    compliance_path = (
        pathlib.Path(__file__).parent.parent / "ai_orchestrator" / "browser_tool" / "policy" / "site_compliance_policy.py"
    )
    assert compliance_path.exists(), "site_compliance_policy.py 파일 없음"


# ── 32. approval/audit policy와 충돌 없음 ────────────────────────────────────


def test_no_conflict_with_approval_audit_policy():
    source = MODULE_PATH.read_text(encoding="utf-8")
    # 승인 없이 실행하는 코드가 없어야 함
    assert "safe_to_execute = True" not in source
    assert "safe_to_dispatch = True" not in source


# ── validate_user_present_flow_result 테스트 ────────────────────────────────


def test_validate_result_detects_missing_fields():
    result = {"local_agent_decision": "REQUIRE_USER_PRESENT"}
    errors = validate_user_present_flow_result(result)
    assert len(errors) > 0


def test_validate_result_passes_valid_task():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "workflow_run_id": "run_validate_001",
    }
    task = build_user_present_task(payload)
    errors = validate_user_present_flow_result(task)
    assert errors == [], f"유효한 task에서 오류 발생: {errors}"


# ── build_local_agent_instruction 민감정보 미포함 ────────────────────────────


def test_local_agent_instruction_no_sensitive_fields():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "workflow_run_id": "run_inst_001",
        "password": "should_not_appear",
        "token": "should_not_appear",
        "cookie": "should_not_appear",
    }
    instruction = build_local_agent_instruction(payload)
    for key in ("password", "token", "cookie", "secret", "otp", "certificate_password"):
        assert key not in instruction, f"instruction에 민감 필드 '{key}' 포함됨"


# ── build_admin_visible_status 테스트 ────────────────────────────────────────


def test_admin_visible_status_contains_required_fields():
    payload = {
        "site_category": "bank",
        "requires_certificate": True,
        "requires_password": True,
        "requires_financial_certificate": False,
        "requires_otp": False,
        "requires_captcha": False,
        "requires_security_plugin": False,
        "workflow_id": "wf_admin_test",
        "workflow_run_id": "run_admin_001",
        "tenant_id": "t001",
        "user_id": "u001",
        "site_id": "s001",
    }
    status = build_admin_visible_status(payload)
    assert "workflow_id" in status
    assert "tenant_id" in status
    assert "execution_location" in status
    assert status.get("safe_to_execute") is False
