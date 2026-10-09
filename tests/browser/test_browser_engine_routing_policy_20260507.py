"""
Browser Engine Routing Policy 테스트

실제 브라우저 접속 없음.
click/type/fill/submit 없음.
쿠키/session/token 추출 없음.
DB write 없음.
dispatcher/task_executor 실제 연결 없음.
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.routing.browser_engine_routing_policy import (
    ENGINE_SEL_API_CONNECTOR,
    ENGINE_SEL_LOCAL_SYSTEM_BROWSER,
    ENGINE_SEL_NONE,
    ENGINE_SEL_SERVER_PLAYWRIGHT,
    ROUTING_API_CONNECTOR,
    ROUTING_BLOCK,
    ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
    ROUTING_MANUAL_REVIEW,
    ROUTING_SERVER_PLAYWRIGHT_READONLY,
    evaluate_browser_engine_routing,
    should_attempt_server_playwright_first,
    should_fallback_to_local_agent,
    validate_browser_engine_routing_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_engine_routing_policy_20260507.json"

MODULE_PATH = Path(__file__).parent.parent.parent / "ai_orchestrator" / "browser_tool" / "routing" / "browser_engine_routing_policy.py"


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixture_cases(fixture_data):
    return {c["id"]: c for c in fixture_data["cases"]}


# ── 1. fixture JSON 로드 가능 ─────────────────────────────────────────────────


def test_fixture_loads(fixture_data):
    assert "cases" in fixture_data
    assert len(fixture_data["cases"]) >= 22


# ── 2. 모든 케이스 필수 section 존재 ─────────────────────────────────────────


def test_all_cases_have_required_sections(fixture_cases):
    required = [
        "id",
        "input",
        "expected_classification",
        "expected_routing",
        "expected_fallback_policy",
        "expected_security_policy",
    ]
    for case_id, case in fixture_cases.items():
        for field in required:
            assert field in case, f"케이스 {case_id}에 필수 필드 없음: {field}"


# ── 3. about:blank → server_playwright route ─────────────────────────────────


def test_about_blank_routes_server_playwright(fixture_cases):
    case = fixture_cases["about_blank_routes_server_playwright"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_SERVER_PLAYWRIGHT_READONLY
    assert result["selected_engine"] == ENGINE_SEL_SERVER_PLAYWRIGHT
    assert result["server_playwright_first_allowed"] is True


# ── 4. data URL → server_playwright route ────────────────────────────────────


def test_data_url_routes_server_playwright(fixture_cases):
    case = fixture_cases["data_url_routes_server_playwright"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_SERVER_PLAYWRIGHT_READONLY
    assert result["server_playwright_first_allowed"] is True


# ── 5. example.com → server_playwright route ─────────────────────────────────


def test_example_com_routes_server_playwright(fixture_cases):
    case = fixture_cases["example_com_routes_server_playwright"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_SERVER_PLAYWRIGHT_READONLY
    assert result["server_playwright_first_allowed"] is True


# ── 6. G2B 공개 read-only → server/API 후보 ──────────────────────────────────


def test_g2b_public_readonly_routes_server_or_api(fixture_cases):
    case = fixture_cases["g2b_public_readonly_routes_server_or_api"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] in (ROUTING_SERVER_PLAYWRIGHT_READONLY, ROUTING_API_CONNECTOR)


# ── 7. runtime failure → 허용 사이트에서만 local fallback 가능 ───────────────


def test_server_playwright_runtime_failure_fallback_allowed(fixture_cases):
    case = fixture_cases["server_playwright_runtime_failure_fallback_local_agent"]
    allowed = should_fallback_to_local_agent(case["input"], failure_reason="runtime_error")
    assert allowed is True


# ── 8. policy blocked failure → fallback 불가 ────────────────────────────────


def test_policy_blocked_failure_no_fallback(fixture_cases):
    case = fixture_cases["server_playwright_policy_block_no_fallback"]
    allowed = should_fallback_to_local_agent(case["input"], failure_reason="policy_blocked")
    assert allowed is False


# ── 9. Google accounts → server playwright first try 금지 ────────────────────


def test_google_accounts_no_server_playwright_first(fixture_cases):
    case = fixture_cases["google_accounts_routes_block_or_api_no_playwright"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["server_playwright_first_allowed"] is False
    assert result["routing_decision"] in (ROUTING_BLOCK, ROUTING_API_CONNECTOR)
    assert should_attempt_server_playwright_first(case["input"]) is False


# ── 10. Gmail → API_CONNECTOR ────────────────────────────────────────────────


def test_gmail_routes_api_connector(fixture_cases):
    case = fixture_cases["gmail_routes_api_connector"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_API_CONNECTOR
    assert result["selected_engine"] == ENGINE_SEL_API_CONNECTOR
    assert result["server_playwright_first_allowed"] is False


# ── 11. Drive → API_CONNECTOR ────────────────────────────────────────────────


def test_drive_routes_api_connector(fixture_cases):
    case = fixture_cases["drive_routes_api_connector"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_API_CONNECTOR
    assert result["selected_engine"] == ENGINE_SEL_API_CONNECTOR


# ── 12. 은행 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ─────────────────────────────


def test_bank_routes_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["bank_routes_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["selected_engine"] == ENGINE_SEL_LOCAL_SYSTEM_BROWSER
    assert result["server_playwright_first_allowed"] is False
    assert result["user_present_required"] is True


# ── 13. 카드사 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ───────────────────────────


def test_card_routes_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["card_routes_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 14. 홈택스 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ───────────────────────────


def test_hometax_routes_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["hometax_routes_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 15. 정부24 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ───────────────────────────


def test_gov24_routes_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["gov24_routes_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 16. 4대보험 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ──────────────────────────


def test_four_insurance_routes_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["four_insurance_routes_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 17. 인증서 사이트 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ────────────────────


def test_certificate_portal_routes_user_present(fixture_cases):
    case = fixture_cases["certificate_portal_routes_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 18. OTP 필요 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ─────────────────────────


def test_otp_required_routes_user_present(fixture_cases):
    case = fixture_cases["otp_required_routes_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 19. password 필요 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ────────────────────


def test_password_required_routes_user_present(fixture_cases):
    case = fixture_cases["password_required_routes_user_present"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 20. CAPTCHA → BLOCK ──────────────────────────────────────────────────────


def test_captcha_routes_block(fixture_cases):
    case = fixture_cases["captcha_routes_block"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_BLOCK
    assert result["selected_engine"] == ENGINE_SEL_NONE


# ── 21. unknown site → MANUAL_REVIEW ─────────────────────────────────────────


def test_unknown_site_routes_manual_review(fixture_cases):
    case = fixture_cases["unknown_site_routes_manual_review"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_MANUAL_REVIEW
    assert result["manual_review_required"] is True


# ── 22. production_mode=true → BLOCK ─────────────────────────────────────────


def test_production_mode_routes_block(fixture_cases):
    case = fixture_cases["production_mode_routes_block"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_BLOCK
    assert result["safe_to_execute"] is False


# ── 23. type operation → 자동 실행 route 금지 ────────────────────────────────


def test_type_operation_blocks_automation(fixture_cases):
    case = fixture_cases["type_operation_blocks_automation"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_BLOCK
    assert result["automation_blocked"] is True


# ── 24. submit operation → 자동 실행 route 금지 ──────────────────────────────


def test_submit_operation_blocks_automation(fixture_cases):
    case = fixture_cases["submit_operation_blocks_automation"]
    result = evaluate_browser_engine_routing(case["input"])
    assert result["routing_decision"] == ROUTING_BLOCK
    assert result["automation_blocked"] is True


# ── 25. safe_to_execute 모든 케이스 False ────────────────────────────────────


def test_safe_to_execute_always_false(fixture_cases):
    for case_id, case in fixture_cases.items():
        result = evaluate_browser_engine_routing(case["input"])
        assert result["safe_to_execute"] is False, f"케이스 {case_id}: safe_to_execute가 False가 아님"


# ── 26. cookie/session/token 추출 코드 없음 ──────────────────────────────────


def test_no_cookie_session_token_extraction():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "cookies()",
        "storage_state()",
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "get_cookies",
        "extract_cookie",
    ]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 코드 발견: {keyword}"


# ── 27. password/otp/certificate_password 입력 코드 없음 ─────────────────────


def test_no_credential_input_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["fill(", ".type(", "keyboard.type", "certificate_password", "otp_input", "password_input"]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 코드 발견: {keyword}"


# ── 28. click/type/fill/submit 호출 없음 ─────────────────────────────────────


def test_no_browser_action_calls():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["page.click(", "page.type(", "page.fill(", "page.submit(", "locator.click", "locator.fill"]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 코드 발견: {keyword}"


# ── 29. browser_engine_capability_classifier와 호환 ──────────────────────────


def test_compatible_with_capability_classifier():
    from ai_orchestrator.browser_tool.routing.browser_engine_capability_classifier import (
        classify_browser_engine_capability,
    )

    payload = {"target_url": "about:blank", "production_mode": False}
    cls_result = classify_browser_engine_capability(payload)
    route_result = evaluate_browser_engine_routing(payload)
    assert cls_result["safe_to_execute"] is False
    assert route_result["safe_to_execute"] is False
    assert route_result["routing_decision"] == ROUTING_SERVER_PLAYWRIGHT_READONLY


# ── 30. server_browser_boundary_policy와 충돌 없음 ───────────────────────────


def test_no_conflict_with_server_browser_boundary_policy():
    from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
        classify_restricted_site_for_server_browser,
    )

    result = classify_restricted_site_for_server_browser({"site_category": "bank"})
    assert result["server_browser_allowed"] is False
    assert result["safe_to_execute"] is False


# ── 31. site_compliance_policy와 충돌 없음 ───────────────────────────────────


def test_no_conflict_with_site_compliance_policy():
    from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance

    # Gmail 은 CDP_READ_ONLY 완화 정책(5177645b): 읽기 = ALLOW_BROWSER_READONLY, 쓰기성 = BLOCK
    result = evaluate_site_compliance({"target_domain": "mail.google.com", "operation_type": "read"})
    assert result["compliance_decision"] == "ALLOW_BROWSER_READONLY"
    assert result["safe_to_execute"] is False
    write = evaluate_site_compliance({"target_domain": "mail.google.com", "operation_type": "send"})
    assert write["compliance_decision"] == "BLOCK"
    assert write["safe_to_dispatch"] is False


# ── 32. local_agent_user_present_flow와 충돌 없음 ────────────────────────────


def test_no_conflict_with_local_agent_user_present_flow():
    from ai_orchestrator.agent_hub.user_present_flow import (
        DECISION_REQUIRE_USER_PRESENT,
    )

    assert DECISION_REQUIRE_USER_PRESENT == "REQUIRE_USER_PRESENT"


# ── 33. DB write 코드 없음 ────────────────────────────────────────────────────


def test_no_db_write_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "session.add(",
        "session.commit(",
        ".save(",
        "db.write",
        "jsonlines.open",
    ]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 DB write 코드 발견: {keyword}"


# ── validate_browser_engine_routing_result 검증 ──────────────────────────────


def test_validate_result_passes_for_valid_cases(fixture_cases):
    for case_id, case in fixture_cases.items():
        result = evaluate_browser_engine_routing(case["input"])
        errors = validate_browser_engine_routing_result(result)
        assert errors == [], f"케이스 {case_id} 검증 오류: {errors}"


# ── should_attempt_server_playwright_first 검증 ──────────────────────────────


def test_should_attempt_server_playwright_first_allowed():
    assert (
        should_attempt_server_playwright_first(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        is True
    )


def test_should_attempt_server_playwright_first_blocked_for_bank():
    assert (
        should_attempt_server_playwright_first(
            {"site_category": "bank", "requires_certificate": True, "operation_type": "read", "production_mode": False}
        )
        is False
    )


def test_should_attempt_server_playwright_first_blocked_for_type_operation():
    assert (
        should_attempt_server_playwright_first(
            {"target_url": "about:blank", "operation_type": "type", "production_mode": False}
        )
        is False
    )


# ── should_fallback_to_local_agent 검증 ──────────────────────────────────────


def test_should_fallback_to_local_agent_allowed_for_runtime_error():
    assert (
        should_fallback_to_local_agent(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False},
            failure_reason="runtime_error",
        )
        is True
    )


def test_should_fallback_to_local_agent_blocked_for_auth_required():
    assert (
        should_fallback_to_local_agent(
            {"site_category": "bank", "requires_certificate": True, "production_mode": False},
            failure_reason="auth_required",
        )
        is False
    )


def test_should_fallback_to_local_agent_blocked_for_certificate_required():
    assert (
        should_fallback_to_local_agent(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False},
            failure_reason="certificate_required",
        )
        is False
    )
