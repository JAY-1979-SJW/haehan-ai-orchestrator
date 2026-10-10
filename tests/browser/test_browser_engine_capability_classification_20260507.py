"""
Browser Engine Capability Classification 테스트

실제 브라우저 접속 없음.
click/type/fill/submit 없음.
쿠키/session/token 추출 없음.
DB write 없음.
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.routing.browser_engine_capability_classifier import (
    ENGINE_API_CONNECTOR_REQUIRED,
    ENGINE_AUTOMATION_BLOCKED,
    ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    ENGINE_NEEDS_MANUAL_REVIEW,
    ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED,
    ROUTE_API_CONNECTOR,
    ROUTE_BLOCK,
    ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY,
    ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
    ROUTE_MANUAL_REVIEW,
    ROUTE_SERVER_PLAYWRIGHT_READONLY,
    classify_browser_engine_capability,
    get_recommended_execution_route,
    validate_engine_capability_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_engine_capability_classification_20260507.json"

MODULE_PATH = (
    Path(__file__).parent.parent.parent / "ai_orchestrator" / "browser_tool" / "routing" / "browser_engine_capability_classifier.py"
)


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
    assert len(fixture_data["cases"]) >= 20


# ── 2. 모든 케이스 필수 section 존재 ─────────────────────────────────────────


def test_all_cases_have_required_sections(fixture_cases):
    required = [
        "id",
        "input",
        "expected_classification",
        "expected_route",
        "expected_fallback_policy",
        "expected_security_policy",
    ]
    for case_id, case in fixture_cases.items():
        for field in required:
            assert field in case, f"케이스 {case_id}에 필수 필드 없음: {field}"


# ── 3. about:blank → SERVER_PLAYWRIGHT_READONLY_ALLOWED ──────────────────────


def test_about_blank_server_playwright_allowed(fixture_cases):
    case = fixture_cases["about_blank_server_playwright_allowed"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED
    assert result["recommended_route"] == ROUTE_SERVER_PLAYWRIGHT_READONLY
    assert result["server_playwright_allowed"] is True


# ── 4. data URL → SERVER_PLAYWRIGHT_READONLY_ALLOWED ─────────────────────────


def test_data_url_server_playwright_allowed(fixture_cases):
    case = fixture_cases["data_url_server_playwright_allowed"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED
    assert result["server_playwright_allowed"] is True


# ── 5. example.com → SERVER_PLAYWRIGHT_READONLY_ALLOWED ──────────────────────


def test_example_com_server_playwright_allowed(fixture_cases):
    case = fixture_cases["example_com_server_playwright_allowed"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED
    assert result["server_playwright_allowed"] is True


# ── 6. G2B 공개 read-only → server playwright 또는 API 후보 ──────────────────


def test_g2b_public_readonly_server_playwright_or_api(fixture_cases):
    case = fixture_cases["g2b_public_notice_server_playwright_or_api_allowed"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] in (
        ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED,
        ENGINE_API_CONNECTOR_REQUIRED,
    )


# ── 7. Google accounts → server/local Playwright 금지 ────────────────────────


def test_google_accounts_no_playwright(fixture_cases):
    case = fixture_cases["google_accounts_api_or_block_no_playwright"]
    result = classify_browser_engine_capability(case["input"])
    assert result["server_playwright_allowed"] is False
    assert result["local_agent_playwright_allowed"] is False
    assert result["recommended_route"] in (ROUTE_BLOCK, ROUTE_API_CONNECTOR)


# ── 8. Gmail → API_CONNECTOR ─────────────────────────────────────────────────


def test_gmail_api_connector(fixture_cases):
    case = fixture_cases["gmail_api_connector_required"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_API_CONNECTOR_REQUIRED
    assert result["recommended_route"] == ROUTE_API_CONNECTOR


# ── 9. Google Drive → API_CONNECTOR ──────────────────────────────────────────


def test_google_drive_api_connector(fixture_cases):
    case = fixture_cases["google_drive_api_connector_required"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_API_CONNECTOR_REQUIRED
    assert result["recommended_route"] == ROUTE_API_CONNECTOR


# ── 10. 은행 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ─────────────────────────────


def test_bank_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["bank_requires_local_system_browser_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["recommended_route"] == ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["user_present_required"] is True


# ── 11. 카드사 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ───────────────────────────


def test_card_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["card_requires_local_system_browser_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 12. 홈택스 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ───────────────────────────


def test_hometax_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["hometax_requires_local_system_browser_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 13. 정부24 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ───────────────────────────


def test_gov24_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["gov24_requires_local_system_browser_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 14. 4대보험 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ──────────────────────────


def test_four_insurance_local_system_browser_user_present(fixture_cases):
    case = fixture_cases["four_insurance_requires_local_system_browser_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 15. 공동인증서 사이트 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ─────────────────


def test_certificate_portal_user_present(fixture_cases):
    case = fixture_cases["certificate_portal_requires_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 16. OTP 필요 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ─────────────────────────


def test_otp_required_user_present(fixture_cases):
    case = fixture_cases["otp_required_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 17. password 필요 → LOCAL_SYSTEM_BROWSER_USER_PRESENT ────────────────────


def test_password_required_user_present(fixture_cases):
    case = fixture_cases["password_required_user_present"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    assert result["user_present_required"] is True


# ── 18. CAPTCHA → AUTOMATION_BLOCKED ─────────────────────────────────────────


def test_captcha_automation_blocked(fixture_cases):
    case = fixture_cases["captcha_automation_blocked"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_AUTOMATION_BLOCKED
    assert result["recommended_route"] == ROUTE_BLOCK


# ── 19. unknown site → NEEDS_MANUAL_REVIEW ───────────────────────────────────


def test_unknown_site_needs_manual_review(fixture_cases):
    case = fixture_cases["unknown_site_needs_manual_review"]
    result = classify_browser_engine_capability(case["input"])
    assert result["engine_capability"] == ENGINE_NEEDS_MANUAL_REVIEW
    assert result["recommended_route"] == ROUTE_MANUAL_REVIEW


# ── 20. 정책 차단 사이트는 server Playwright first try 금지 ──────────────────


def test_policy_blocked_site_no_server_playwright_first(fixture_cases):
    case = fixture_cases["policy_blocked_site_cannot_try_server_playwright_first"]
    result = classify_browser_engine_capability(case["input"])
    assert result["server_playwright_allowed"] is False
    assert result["recommended_route"] != ROUTE_SERVER_PLAYWRIGHT_READONLY


# ── 21. 허용 사이트에서 서버 Playwright runtime failure → fallback 가능 ───────


def test_allowed_site_server_playwright_fallback_available(fixture_cases):
    case = fixture_cases["server_playwright_runtime_failure_can_fallback_for_allowed_site"]
    result = classify_browser_engine_capability(case["input"])
    assert result["fallback_allowed"] is True
    assert result["fallback_route"] == ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY


# ── 22. safe_to_execute 모든 케이스 False ────────────────────────────────────


def test_safe_to_execute_always_false(fixture_cases):
    for case_id, case in fixture_cases.items():
        result = classify_browser_engine_capability(case["input"])
        assert result["safe_to_execute"] is False, f"케이스 {case_id}: safe_to_execute가 False가 아님"


# ── 23. cookie/session/token 추출 코드 없음 ──────────────────────────────────


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


# ── 24. password/otp/certificate_password 입력 코드 없음 ─────────────────────


def test_no_credential_input_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["fill(", "type(", ".type(", "keyboard.type", "certificate_password", "otp_input", "password_input"]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 코드 발견: {keyword}"


# ── 25. click/type/fill/submit 호출 없음 ─────────────────────────────────────


def test_no_browser_action_calls():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "page.click(",
        "page.type(",
        "page.fill(",
        "page.submit(",
        ".click(",
        ".fill(",
        "locator.click",
        "locator.fill",
    ]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 코드 발견: {keyword}"


# ── 26. server_browser_boundary_policy와 충돌 없음 ───────────────────────────


def test_no_conflict_with_server_browser_boundary_policy():
    from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
        classify_restricted_site_for_server_browser,
    )

    result = classify_restricted_site_for_server_browser({"site_category": "g2b_public_readonly"})
    assert "server_browser_decision" in result
    assert result["safe_to_execute"] is False


# ── 27. site_compliance_policy와 충돌 없음 ───────────────────────────────────


def test_no_conflict_with_site_compliance_policy():
    from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance

    result = evaluate_site_compliance({"target_domain": "example.com", "operation_type": "read"})
    assert "compliance_decision" in result
    assert result["safe_to_execute"] is False


# ── 28. site_access_compatibility_auditor와 충돌 없음 ────────────────────────


def test_no_conflict_with_site_access_compatibility_auditor():
    from ai_orchestrator.browser_tool.policy.site_access_compatibility_auditor import (
        evaluate_site_access_policy,
    )

    result = evaluate_site_access_policy(
        {
            "site_id": "test",
            "site_name": "Test",
            "base_domain": "example.com",
            "category": "procurement",
        }
    )
    assert "final_verdict" in result
    assert result["safe_to_execute"] is False


# ── 29. local_agent_user_present_flow와 충돌 없음 ────────────────────────────


def test_no_conflict_with_local_agent_user_present_flow():
    from ai_orchestrator.agent_hub.user_present_flow import (
        DECISION_REQUIRE_USER_PRESENT,
    )

    assert DECISION_REQUIRE_USER_PRESENT == "REQUIRE_USER_PRESENT"


# ── 30. DB write 코드 없음 ────────────────────────────────────────────────────


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


# ── validate_engine_capability_result 검증 ───────────────────────────────────


def test_validate_result_passes_for_valid_cases(fixture_cases):
    for case_id, case in fixture_cases.items():
        result = classify_browser_engine_capability(case["input"])
        errors = validate_engine_capability_result(result)
        assert errors == [], f"케이스 {case_id} 검증 오류: {errors}"


# ── get_recommended_execution_route 반환값 검증 ──────────────────────────────


def test_get_recommended_execution_route_returns_route():
    payload = {
        "site_category": "example",
        "target_domain": "example.com",
        "target_url": "https://example.com/",
        "production_mode": False,
    }
    result = get_recommended_execution_route(payload)
    assert "recommended_route" in result
    assert result["safe_to_execute"] is False


# ── production_mode=true → BLOCK ─────────────────────────────────────────────


def test_production_mode_always_block():
    payload = {
        "site_category": "example",
        "target_domain": "example.com",
        "target_url": "https://example.com/",
        "production_mode": True,
    }
    result = classify_browser_engine_capability(payload)
    assert result["recommended_route"] == ROUTE_BLOCK
    assert result["safe_to_execute"] is False
