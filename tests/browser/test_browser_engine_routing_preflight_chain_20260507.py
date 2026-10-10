"""
Browser Engine Routing Preflight Chain 테스트

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
    should_fallback_to_local_agent,
)
from ai_orchestrator.browser_tool.routing.browser_engine_routing_preflight_chain import (
    CHAIN_APPROVAL_REQUIRED,
    CHAIN_BLOCK,
    CHAIN_MANUAL_REVIEW_REQUIRED,
    CHAIN_PROCEED,
    CHAIN_ROUTE_API_CONNECTOR,
    CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER,
    NEXT_API_CONNECTOR,
    NEXT_APPROVAL_REQUIRED,
    NEXT_BLOCKED,
    NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
    NEXT_MANUAL_REVIEW_REQUIRED,
    NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT,
    build_next_step_instruction,
    evaluate_browser_engine_routing_preflight_chain,
    validate_routing_preflight_chain_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_engine_routing_preflight_chain_20260507.json"
MODULE_PATH = (
    Path(__file__).parent.parent.parent / "ai_orchestrator" / "browser_tool" / "routing" / "browser_engine_routing_preflight_chain.py"
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


# ── 3. about:blank → server readonly preflight 후보 ──────────────────────────


def test_about_blank_server_readonly_chain(fixture_cases):
    case = fixture_cases["about_blank_server_readonly_chain"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT
    assert result["chain_decision"] == CHAIN_PROCEED


# ── 4. example.com → server readonly preflight 후보 ──────────────────────────


def test_example_com_server_readonly_chain(fixture_cases):
    case = fixture_cases["example_com_server_readonly_chain"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT


# ── 5. G2B 공개 → server/API 후보 ────────────────────────────────────────────


def test_g2b_public_notice_chain(fixture_cases):
    case = fixture_cases["g2b_public_notice_server_readonly_or_api_chain"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] in (NEXT_SERVER_PLAYWRIGHT_READONLY_PREFLIGHT, NEXT_API_CONNECTOR)


# ── 6. 은행 → 서버 브라우저 체인 진입 없이 user-present ──────────────────────


def test_bank_routes_directly_user_present(fixture_cases):
    case = fixture_cases["bank_routes_directly_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["chain_decision"] == CHAIN_ROUTE_LOCAL_SYSTEM_BROWSER
    # 서버 브라우저 체인(site_compliance 이후)으로 진입하지 않음
    assert result["site_compliance_decision"] == "SKIPPED"
    assert result["server_boundary_decision"] == "SKIPPED"


# ── 7. 카드사 → user-present ──────────────────────────────────────────────────


def test_card_routes_directly_user_present(fixture_cases):
    case = fixture_cases["card_routes_directly_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["site_compliance_decision"] == "SKIPPED"


# ── 8. 홈택스 → user-present ──────────────────────────────────────────────────


def test_hometax_routes_directly_user_present(fixture_cases):
    case = fixture_cases["hometax_routes_directly_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["site_compliance_decision"] == "SKIPPED"


# ── 9. 정부24 → user-present ──────────────────────────────────────────────────


def test_gov24_routes_directly_user_present(fixture_cases):
    case = fixture_cases["gov24_routes_directly_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT


# ── 10. 4대보험 → user-present ────────────────────────────────────────────────


def test_four_insurance_routes_directly_user_present(fixture_cases):
    case = fixture_cases["four_insurance_routes_directly_local_system_browser_user_present"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT


# ── 11. 인증서 사이트 → user-present ─────────────────────────────────────────


def test_certificate_routes_directly_user_present(fixture_cases):
    case = fixture_cases["certificate_routes_directly_user_present"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT


# ── 12. Google accounts → server Playwright로 가지 않음 ──────────────────────


def test_google_accounts_no_server_playwright_chain(fixture_cases):
    case = fixture_cases["google_accounts_block_or_api_no_server_playwright"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_BLOCKED
    assert result["site_compliance_decision"] == "SKIPPED"
    assert result["server_boundary_decision"] == "SKIPPED"


# ── 13. Gmail → API_CONNECTOR ────────────────────────────────────────────────


def test_gmail_routes_api_connector_chain(fixture_cases):
    case = fixture_cases["gmail_routes_api_connector"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_API_CONNECTOR
    assert result["chain_decision"] == CHAIN_ROUTE_API_CONNECTOR


# ── 14. Drive → API_CONNECTOR ────────────────────────────────────────────────


def test_drive_routes_api_connector_chain(fixture_cases):
    case = fixture_cases["drive_routes_api_connector"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_API_CONNECTOR


# ── 15. CAPTCHA → BLOCKED ────────────────────────────────────────────────────


def test_captcha_routes_blocked_chain(fixture_cases):
    case = fixture_cases["captcha_routes_block"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_BLOCKED
    assert result["chain_decision"] == CHAIN_BLOCK


# ── 16. unknown site → MANUAL_REVIEW_REQUIRED ────────────────────────────────


def test_unknown_site_manual_review_chain(fixture_cases):
    case = fixture_cases["unknown_site_manual_review"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_MANUAL_REVIEW_REQUIRED
    assert result["chain_decision"] == CHAIN_MANUAL_REVIEW_REQUIRED


# ── 17. production_mode=true → BLOCKED ───────────────────────────────────────


def test_production_mode_blocked_chain(fixture_cases):
    case = fixture_cases["production_mode_block"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_BLOCKED


# ── 18. type operation → BLOCKED ─────────────────────────────────────────────


def test_type_operation_blocked_chain(fixture_cases):
    case = fixture_cases["type_operation_block"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_BLOCKED
    assert result["chain_decision"] == CHAIN_BLOCK


# ── 19. submit operation → BLOCKED ───────────────────────────────────────────


def test_submit_operation_blocked_chain(fixture_cases):
    case = fixture_cases["submit_operation_block"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_BLOCKED
    assert result["chain_decision"] == CHAIN_BLOCK


# ── 20. approval_required → APPROVAL_REQUIRED에서 chain 멈춤 ─────────────────


def test_approval_required_chain_stops(fixture_cases):
    case = fixture_cases["approval_required_chain_stops_before_dispatch"]
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_APPROVAL_REQUIRED
    assert result["chain_decision"] == CHAIN_APPROVAL_REQUIRED
    assert result["should_write_audit"] is True


# ── 21. API connector route → Playwright preflight 진입 안 함 ────────────────


def test_api_connector_no_playwright_preflight():
    payload = {
        "site_category": "gmail",
        "target_domain": "mail.google.com",
        "target_url": "https://mail.google.com/",
        "operation_type": "read",
    }
    result = evaluate_browser_engine_routing_preflight_chain(payload)
    assert result["next_step"] == NEXT_API_CONNECTOR
    # site compliance, server boundary 단계 건너뜀
    assert result["site_compliance_decision"] == "SKIPPED"
    assert result["server_boundary_decision"] == "SKIPPED"


# ── 22. policy_blocked → fallback 불가 ───────────────────────────────────────


def test_policy_blocked_no_fallback(fixture_cases):
    case = fixture_cases["policy_blocked_no_fallback"]
    allowed = should_fallback_to_local_agent(case["input"], failure_reason="policy_blocked")
    assert allowed is False
    result = evaluate_browser_engine_routing_preflight_chain(case["input"])
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT


# ── 23. runtime failure fallback → 허용 사이트만 가능 ────────────────────────


def test_runtime_failure_fallback_only_for_allowed_site(fixture_cases):
    case = fixture_cases["runtime_failure_allowed_fallback_only_for_allowed_site"]
    allowed = should_fallback_to_local_agent(case["input"], failure_reason="runtime_error")
    assert allowed is True
    # 은행에서는 fallback 불가
    bank_payload = {"site_category": "bank", "requires_certificate": True, "production_mode": False}
    assert should_fallback_to_local_agent(bank_payload, failure_reason="runtime_error") is False


# ── 24. safe_to_execute 모든 케이스 False ────────────────────────────────────


def test_safe_to_execute_always_false(fixture_cases):
    for case_id, case in fixture_cases.items():
        result = evaluate_browser_engine_routing_preflight_chain(case["input"])
        assert result["safe_to_execute"] is False, f"케이스 {case_id}: safe_to_execute가 False가 아님"


# ── 25. next_step_instruction에 secret/token/cookie/session 없음 ─────────────


def test_next_step_instruction_no_sensitive_data(fixture_cases):
    forbidden = ["secret", "token", "cookie", "session", "password", "otp", "certificate_password"]
    for case_id, case in fixture_cases.items():
        result = evaluate_browser_engine_routing_preflight_chain(case["input"])
        instruction = result.get("next_step_instruction", {})
        instruction_str = str(instruction).lower()
        for keyword in forbidden:
            assert keyword not in instruction_str, (
                f"케이스 {case_id} next_step_instruction에 금지된 키워드 발견: {keyword}"
            )


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


# ── 29. DB write 코드 없음 ────────────────────────────────────────────────────


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


# ── 30. 기존 classifier와 호환 ───────────────────────────────────────────────


def test_compatible_with_capability_classifier():
    from ai_orchestrator.browser_tool.routing.browser_engine_capability_classifier import (
        classify_browser_engine_capability,
    )

    payload = {"target_url": "about:blank", "operation_type": "read"}
    cls = classify_browser_engine_capability(payload)
    chain = evaluate_browser_engine_routing_preflight_chain(payload)
    assert cls["safe_to_execute"] is False
    assert chain["safe_to_execute"] is False
    assert chain["engine_capability"] == cls["engine_capability"]


# ── 31. 기존 routing policy와 호환 ───────────────────────────────────────────


def test_compatible_with_routing_policy():
    from ai_orchestrator.browser_tool.routing.browser_engine_routing_policy import (
        evaluate_browser_engine_routing,
    )

    payload = {"site_category": "bank", "requires_certificate": True, "operation_type": "read"}
    routing = evaluate_browser_engine_routing(payload)
    chain = evaluate_browser_engine_routing_preflight_chain(payload)
    assert routing["safe_to_execute"] is False
    assert chain["safe_to_execute"] is False
    assert chain["routing_decision"] == routing["routing_decision"]


# ── 32. 기존 server_boundary_policy와 충돌 없음 ──────────────────────────────


def test_no_conflict_with_server_boundary_policy():
    from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
        classify_restricted_site_for_server_browser,
    )

    result = classify_restricted_site_for_server_browser({"site_category": "bank"})
    assert result["server_browser_allowed"] is False
    assert result["safe_to_execute"] is False


# ── 33. 기존 site_compliance_policy와 충돌 없음 ──────────────────────────────


def test_no_conflict_with_site_compliance_policy():
    from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance

    # Gmail 은 CDP_READ_ONLY 완화 정책(5177645b): 읽기 = ALLOW_BROWSER_READONLY, 쓰기성 = BLOCK
    result = evaluate_site_compliance({"target_domain": "mail.google.com", "operation_type": "read"})
    assert result["compliance_decision"] == "ALLOW_BROWSER_READONLY"
    assert result["safe_to_execute"] is False
    write = evaluate_site_compliance({"target_domain": "mail.google.com", "operation_type": "send"})
    assert write["compliance_decision"] == "BLOCK"
    assert write["safe_to_dispatch"] is False


# ── 34. local_agent_user_present_flow와 충돌 없음 ────────────────────────────


def test_no_conflict_with_local_agent_user_present_flow():
    from ai_orchestrator.agent_hub.user_present_flow import (
        DECISION_REQUIRE_USER_PRESENT,
    )

    assert DECISION_REQUIRE_USER_PRESENT == "REQUIRE_USER_PRESENT"


# ── 35. validate_routing_preflight_chain_result 검증 ─────────────────────────


def test_validate_result_passes_for_all_fixture_cases(fixture_cases):
    for case_id, case in fixture_cases.items():
        result = evaluate_browser_engine_routing_preflight_chain(case["input"])
        errors = validate_routing_preflight_chain_result(result)
        assert errors == [], f"케이스 {case_id} 검증 오류: {errors}"


# ── 36. build_next_step_instruction 반환값 검증 ──────────────────────────────


def test_build_next_step_instruction_safe_to_execute_false():
    payload = {"target_url": "about:blank", "operation_type": "read"}
    result = evaluate_browser_engine_routing_preflight_chain(payload)
    instruction = build_next_step_instruction(result)
    assert instruction["safe_to_execute"] is False
    assert "next_step" in instruction
    assert "chain_decision" in instruction


# ── 37. 허용 사이트에서만 safe_to_dispatch=True 가능 ─────────────────────────


def test_safe_to_dispatch_only_for_chain_proceed():
    # 통과한 경우
    result_pass = evaluate_browser_engine_routing_preflight_chain(
        {"target_url": "about:blank", "operation_type": "read"}
    )
    assert result_pass["safe_to_dispatch"] is True
    # 차단된 경우
    result_block = evaluate_browser_engine_routing_preflight_chain(
        {"site_category": "bank", "requires_certificate": True, "operation_type": "read"}
    )
    assert result_block["safe_to_dispatch"] is False


# ── 38. OTP 필요 → user-present ──────────────────────────────────────────────


def test_otp_required_routes_user_present():
    result = evaluate_browser_engine_routing_preflight_chain(
        {"requires_otp": True, "operation_type": "read", "production_mode": False}
    )
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["safe_to_execute"] is False


# ── 39. password 필요 → user-present ─────────────────────────────────────────


def test_password_required_routes_user_present():
    result = evaluate_browser_engine_routing_preflight_chain(
        {"requires_password": True, "operation_type": "read", "production_mode": False}
    )
    assert result["next_step"] == NEXT_LOCAL_SYSTEM_BROWSER_USER_PRESENT
    assert result["safe_to_execute"] is False


# ── 40. dispatcher 연결 코드 없음 ────────────────────────────────────────────


def test_no_dispatcher_connection_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["dispatch_task(", "run_workflow(", "execute_action(", "TaskExecutor("]
    for keyword in forbidden:
        assert keyword not in source, f"모듈에 금지된 dispatcher 코드 발견: {keyword}"
