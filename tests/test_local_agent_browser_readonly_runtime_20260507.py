"""
로컬 Agent read-only 브라우저 런타임 테스트

click/type/submit/쿠키추출은 절대 없어야 한다.
safe_to_execute는 항상 False다.
"""

import json
import pathlib

import pytest

from core.agent_runtime.browser.browser_readonly_runtime import (
    DECISION_BLOCK,
    DECISION_FAILED,
    DECISION_READONLY_ALLOWED,
    DECISION_REQUIRE_API,
    DECISION_REQUIRE_USER_PRESENT,
    DECISION_RUNTIME_NOT_AVAILABLE,
    _detect_auth_methods,
    _detect_security_requirements,
    _hash_url,
    _redact_snippet,
    _redact_url,
    build_readonly_browser_result,
    build_readonly_browser_task,
    evaluate_readonly_browser_permission,
    execute_readonly_browser_task,
    redact_readonly_browser_result,
    validate_readonly_browser_result,
)

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "local_agent_browser_readonly_runtime_20260507.json"
MODULE_PATH = pathlib.Path(__file__).parent.parent / "core" / "agent_runtime" / "browser" / "browser_readonly_runtime.py"

REQUIRED_CASE_FIELDS = ["case_id", "input", "expected_runtime_policy", "expected_detection", "expected_security_policy"]
REQUIRED_POLICY_FIELDS = [
    "runtime_decision",
    "readonly_execution",
    "user_present_required",
    "local_agent_required",
    "api_required",
    "safe_to_execute",
    "blocked_reason",
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
    assert len(fixture_data["cases"]) >= 16


# ── 2. 모든 케이스 필수 필드 존재 ───────────────────────────────────────────────


def test_all_cases_have_required_fields(fixture_data):
    for case in fixture_data["cases"]:
        for field in REQUIRED_CASE_FIELDS:
            assert field in case, f"케이스 {case.get('case_id')} 에 필드 '{field}' 없음"
        for field in REQUIRED_POLICY_FIELDS:
            assert field in case["expected_runtime_policy"], (
                f"케이스 {case.get('case_id')} expected_runtime_policy에 '{field}' 없음"
            )


# ── 3. read/navigate/open_url만 readonly 후보 ─────────────────────────────────


def test_allowed_operations_get_readonly_allowed():
    for op in ("read", "navigate", "open_url", "readonly_search", "readonly_scrape", "readonly_status_check"):
        perm = evaluate_readonly_browser_permission(
            {
                "operation_type": op,
                "site_category": "procurement",
                "production_mode": False,
            }
        )
        assert perm["runtime_decision"] == DECISION_READONLY_ALLOWED, f"operation_type={op} should be READONLY_ALLOWED"


# ── 4. click operation은 BLOCK ────────────────────────────────────────────────


def test_click_operation_is_blocked():
    perm = evaluate_readonly_browser_permission(
        {"operation_type": "click", "site_category": "bank", "production_mode": False}
    )
    assert perm["runtime_decision"] == DECISION_BLOCK
    assert "click" in perm["blocked_reason"]


# ── 5. type operation은 BLOCK ─────────────────────────────────────────────────


def test_type_operation_is_blocked():
    perm = evaluate_readonly_browser_permission(
        {"operation_type": "type", "site_category": "bank", "production_mode": False}
    )
    assert perm["runtime_decision"] == DECISION_BLOCK
    assert "type" in perm["blocked_reason"]


# ── 6. submit operation은 BLOCK ───────────────────────────────────────────────


def test_submit_operation_is_blocked():
    perm = evaluate_readonly_browser_permission(
        {"operation_type": "submit", "site_category": "bank", "production_mode": False}
    )
    assert perm["runtime_decision"] == DECISION_BLOCK
    assert "submit" in perm["blocked_reason"]


# ── 7. Google은 REQUIRE_API_CONNECTOR ────────────────────────────────────────


def test_google_cloud_service_is_api_required():
    for category in ("cloud_service", "google", "google_workspace"):
        perm = evaluate_readonly_browser_permission(
            {
                "operation_type": "read",
                "site_category": category,
                "production_mode": False,
            }
        )
        assert perm["runtime_decision"] == DECISION_REQUIRE_API, (
            f"site_category={category} should be REQUIRE_API_CONNECTOR"
        )
        assert perm["api_required"] is True


# ── 8. 공동인증서 감지 시 USER_PRESENT_REQUIRED ──────────────────────────────


def test_certificate_text_detected():
    text = "공동인증서로 로그인하세요. 인증서를 선택하고 비밀번호를 입력하세요."
    detected = _detect_auth_methods(text)
    assert "certificate" in detected


# ── 9. 금융인증서 감지 시 USER_PRESENT_REQUIRED ──────────────────────────────


def test_financial_certificate_text_detected():
    text = "금융인증서로 로그인하세요."
    detected = _detect_auth_methods(text)
    assert "financial_certificate" in detected


# ── 10. OTP 감지 시 USER_PRESENT_REQUIRED ────────────────────────────────────


def test_otp_text_detected():
    text = "OTP 번호를 입력하세요. 일회용 비밀번호를 확인하세요."
    detected = _detect_auth_methods(text)
    assert "otp" in detected


# ── 11. CAPTCHA 감지 시 BLOCK ─────────────────────────────────────────────────


def test_captcha_text_detected_as_blocker():
    text = "CAPTCHA 인증을 완료해 주세요. 보안문자를 입력하세요."
    requirements, blockers = _detect_security_requirements(text)
    assert "captcha" in requirements
    assert "captcha" in blockers


# ── 12. 보안프로그램 감지 시 security_plugin 태그 ────────────────────────────


def test_security_plugin_text_detected():
    text = "보안프로그램을 설치하세요. 키보드보안 프로그램이 필요합니다."
    requirements, blockers = _detect_security_requirements(text)
    assert "security_plugin" in requirements
    assert "captcha" not in blockers  # security_plugin is not a blocker


# ── 13. 원격접속 차단 문구 감지 ──────────────────────────────────────────────


def test_remote_access_warning_detected():
    text = "원격접속 차단 정책이 적용되었습니다. 원격제어 환경에서는 이용할 수 없습니다."
    requirements, blockers = _detect_security_requirements(text)
    assert "remote_access_warning" in requirements


# ── 14. production_mode=true는 BLOCK ─────────────────────────────────────────


def test_production_mode_is_blocked():
    perm = evaluate_readonly_browser_permission(
        {
            "operation_type": "readonly_search",
            "site_category": "procurement",
            "production_mode": True,
        }
    )
    assert perm["runtime_decision"] == DECISION_BLOCK
    assert perm["blocked_reason"] == "PRODUCTION_MODE_BLOCKED"


# ── 15. safe_to_execute는 모든 케이스 false ──────────────────────────────────


def test_safe_to_execute_always_false_in_fixture(fixture_data):
    for case in fixture_data["cases"]:
        assert case["expected_runtime_policy"]["safe_to_execute"] is False, (
            f"safe_to_execute가 False가 아님: {case['case_id']}"
        )


def test_build_task_safe_to_execute_always_false():
    payloads = [
        {"operation_type": "read", "site_category": "bank", "production_mode": False},
        {"operation_type": "submit", "site_category": "bank", "production_mode": False},
        {"operation_type": "read", "site_category": "cloud_service", "production_mode": False},
        {"operation_type": "read", "site_category": "procurement", "production_mode": True},
    ]
    for p in payloads:
        task = build_readonly_browser_task(p)
        assert task["safe_to_execute"] is False, f"safe_to_execute False가 아님: {p}"


def test_build_result_safe_to_execute_always_false():
    result = build_readonly_browser_result(
        {
            "runtime_decision": DECISION_READONLY_ALLOWED,
            "readonly_execution": True,
        }
    )
    assert result["safe_to_execute"] is False
    assert result["safe_to_dispatch"] is False


# ── 16. target_url_hash 생성 ─────────────────────────────────────────────────


def test_target_url_hash_generated():
    url = "https://www.g2b.go.kr/search"
    h = _hash_url(url)
    assert h.startswith("sha256:")
    assert len(h) > 10
    # 동일 URL은 동일 hash
    assert _hash_url(url) == _hash_url(url)
    # 다른 URL은 다른 hash
    assert _hash_url(url) != _hash_url("https://other.co.kr/")


def test_task_contains_url_hash():
    task = build_readonly_browser_task(
        {
            "operation_type": "read",
            "site_category": "procurement",
            "target_url": "https://www.g2b.go.kr/search",
            "production_mode": False,
        }
    )
    assert task["target_url_hash"] is not None
    assert task["target_url_hash"].startswith("sha256:")


# ── 17. target_url_redacted 생성 ─────────────────────────────────────────────


def test_target_url_redacted_generated():
    url = "https://www.bank.co.kr/login?user=admin&pass=secret"
    redacted = _redact_url(url)
    assert "admin" not in redacted
    assert "secret" not in redacted
    assert "[REDACTED]" in redacted


def test_task_contains_url_redacted():
    task = build_readonly_browser_task(
        {
            "operation_type": "read",
            "site_category": "bank",
            "target_url": "https://www.bank.co.kr/login",
            "production_mode": False,
        }
    )
    assert task["target_url_redacted"] is not None
    assert "[REDACTED]" in task["target_url_redacted"]


# ── 18. text_snippet_redacted에 민감정보 없음 ────────────────────────────────


def test_snippet_redacts_sensitive_words():
    raw = "사용자 비밀번호: hunter2 token: abc123 cookie: xyz 일반 텍스트"
    redacted = _redact_snippet(raw)
    # 민감 키워드(비밀번호, token, cookie, session)가 [REDACTED]로 치환됨
    assert "[REDACTED]" in redacted
    # 원문 민감 키워드가 그대로 남아있지 않아야 함
    assert "비밀번호" not in redacted
    assert "token" not in redacted
    assert "cookie" not in redacted


def test_snippet_length_limited():
    long_text = "A" * 1000
    redacted = _redact_snippet(long_text)
    assert len(redacted) <= 500


# ── 19. raw HTML 전체 저장 없음 ──────────────────────────────────────────────


def test_no_raw_html_in_result():
    result = build_readonly_browser_result(
        {
            "runtime_decision": DECISION_READONLY_ALLOWED,
            "readonly_execution": True,
            "raw_html": "<html>sensitive content</html>",
        }
    )
    assert "raw_html" not in result
    assert "html" not in result


# ── 20. screenshot 저장 코드 없음 ────────────────────────────────────────────


def test_no_screenshot_code_in_module():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["screenshot(", ".screenshot(", "save_screenshot(", "take_screenshot("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 screenshot 패턴 '{pattern}' 발견"


# ── 21. cookie/session/token/localStorage 추출 코드 없음 ────────────────────


def test_no_cookie_extraction_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "document.cookie",
        "localStorage.getItem",
        "sessionStorage.getItem",
        "extract_cookie(",
        "get_cookies(",
        "storage_state(",
    ]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 금지 패턴 '{pattern}' 발견"


# ── 22. 인증서 비밀번호 입력 코드 없음 ──────────────────────────────────────


def test_no_certificate_password_input_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["fill_certificate_password(", "type_certificate_password(", "enter_cert_pw("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 금지 패턴 '{pattern}' 발견"


# ── 23. OTP 입력 코드 없음 ──────────────────────────────────────────────────


def test_no_otp_input_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["fill_otp(", "type_otp(", "enter_otp(", "input_otp("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 금지 패턴 '{pattern}' 발견"


# ── 24. click/type/fill/submit 호출 없음 ────────────────────────────────────


def test_no_click_type_fill_submit_calls():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [".click(", ".type(", ".fill(", ".submit(", "page.press("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 Playwright 금지 패턴 '{pattern}' 발견"


# ── 25. DB write 코드 없음 ───────────────────────────────────────────────────


def test_no_db_write_code():
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ["INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE", ".execute(", "db.commit("]
    for pattern in forbidden:
        assert pattern not in source, f"소스에 DB write 패턴 '{pattern}' 발견"


# ── 26. local_agent_user_present_flow와 호환 ─────────────────────────────────


def test_compatible_with_user_present_flow():
    user_present_path = (
        pathlib.Path(__file__).parent.parent / "ai_orchestrator" / "agent_hub" / "user_present_flow.py"
    )
    assert user_present_path.exists(), "local_agent_user_present_flow.py 없음"
    source = MODULE_PATH.read_text(encoding="utf-8")
    # 실행 위치 코드 호환성
    assert "REQUIRE_USER_PRESENT" in source
    assert "READONLY_ALLOWED" in source
    assert "safe_to_execute" in source


# ── 27. site_access_compatibility_auditor와 호환 ─────────────────────────────


def test_compatible_with_site_access_compatibility_auditor():
    auditor_path = (
        pathlib.Path(__file__).parent.parent
        / "ai_orchestrator"
        / "browser_tool"
        / "policy"
        / "site_access_compatibility_auditor.py"
    )
    assert auditor_path.exists(), "site_access_compatibility_auditor.py 없음"


# ── 28. site_compliance_policy와 호환 ────────────────────────────────────────


def test_compatible_with_site_compliance_policy():
    compliance_path = (
        pathlib.Path(__file__).parent.parent / "ai_orchestrator" / "browser_tool" / "policy" / "site_compliance_policy.py"
    )
    assert compliance_path.exists(), "site_compliance_policy.py 없음"


# ── validate_readonly_browser_result 테스트 ──────────────────────────────────


def test_validate_result_detects_missing_fields():
    errors = validate_readonly_browser_result({"runtime_decision": DECISION_READONLY_ALLOWED})
    assert len(errors) > 0


def test_validate_result_passes_valid():
    result = build_readonly_browser_result(
        {
            "runtime_decision": DECISION_READONLY_ALLOWED,
            "readonly_execution": True,
            "user_present_required": False,
            "local_agent_required": True,
            "api_required": False,
        }
    )
    errors = validate_readonly_browser_result(result)
    assert errors == [], f"유효한 result에서 오류 발생: {errors}"


def test_validate_result_detects_safe_to_execute_true():
    result = build_readonly_browser_result({"runtime_decision": DECISION_READONLY_ALLOWED})
    result["safe_to_execute"] = True  # 강제 변조
    errors = validate_readonly_browser_result(result)
    assert any("safe_to_execute" in e for e in errors)


def test_validate_result_detects_forbidden_fields():
    result = build_readonly_browser_result({"runtime_decision": DECISION_READONLY_ALLOWED})
    result["target_url"] = "https://secret.bank.co.kr"
    errors = validate_readonly_browser_result(result)
    assert any("target_url" in e for e in errors)


# ── redact_readonly_browser_result 테스트 ────────────────────────────────────


def test_redact_result_removes_sensitive_fields():
    dirty = {
        "workflow_run_id": "run_001",
        "runtime_decision": DECISION_READONLY_ALLOWED,
        "target_url": "https://secret.bank.co.kr/login",
        "final_url": "https://secret.bank.co.kr/main",
        "raw_html": "<html>...</html>",
        "cookie": "session=abc123",
        "token": "Bearer xyz",
        "password": "hunter2",
    }
    clean = redact_readonly_browser_result(dirty)
    for key in ("target_url", "final_url", "raw_html", "cookie", "token", "password"):
        assert key not in clean, f"redact 후에도 '{key}' 포함됨"
    assert "workflow_run_id" in clean
    assert "runtime_decision" in clean


# ── execute_readonly_browser_task 정책 테스트 (브라우저 없음 환경) ──────────


def test_execute_blocked_operation_returns_block():
    result = execute_readonly_browser_task(
        {
            "operation_type": "click",
            "site_category": "bank",
            "production_mode": False,
            "target_url": "https://bank.co.kr/",
        }
    )
    assert result["runtime_decision"] == DECISION_BLOCK
    assert result["safe_to_execute"] is False


def test_execute_production_mode_returns_block():
    result = execute_readonly_browser_task(
        {
            "operation_type": "read",
            "site_category": "procurement",
            "production_mode": True,
            "target_url": "https://g2b.go.kr/search",
        }
    )
    assert result["runtime_decision"] == DECISION_BLOCK
    assert result["blocked_reason"] == "PRODUCTION_MODE_BLOCKED"
    assert result["safe_to_execute"] is False


def test_execute_api_category_returns_api_required():
    result = execute_readonly_browser_task(
        {
            "operation_type": "read",
            "site_category": "cloud_service",
            "production_mode": False,
            "target_url": "https://googleapis.com/v1/",
        }
    )
    assert result["runtime_decision"] == DECISION_REQUIRE_API
    assert result["safe_to_execute"] is False


def test_execute_readonly_missing_url_returns_block():
    result = execute_readonly_browser_task(
        {
            "operation_type": "read",
            "site_category": "procurement",
            "production_mode": False,
            "target_url": "",
        }
    )
    assert result["runtime_decision"] == DECISION_BLOCK
    assert result["safe_to_execute"] is False


# ── 인증 감지 통합 테스트 ────────────────────────────────────────────────────


def test_detect_combined_auth_in_page():
    text = "공인인증서 또는 금융인증서로 로그인하세요. OTP 인증도 가능합니다."
    detected = _detect_auth_methods(text)
    assert "certificate" in detected
    assert "financial_certificate" in detected
    assert "otp" in detected


def test_detect_simple_auth_methods():
    text = "카카오 인증 또는 PASS 인증으로 간편하게 로그인하세요."
    detected = _detect_auth_methods(text)
    assert "simple_auth" in detected


def test_detect_security_plugin_not_a_blocker():
    text = "보안프로그램을 설치하세요."
    requirements, blockers = _detect_security_requirements(text)
    assert "security_plugin" in requirements
    assert len(blockers) == 0


def test_detect_captcha_is_a_blocker():
    text = "보안문자를 입력해주세요."
    requirements, blockers = _detect_security_requirements(text)
    assert "captcha" in requirements
    assert "captcha" in blockers


# ── fill operation 추가 차단 확인 ────────────────────────────────────────────


def test_fill_operation_is_blocked():
    perm = evaluate_readonly_browser_permission(
        {"operation_type": "fill", "site_category": "bank", "production_mode": False}
    )
    assert perm["runtime_decision"] == DECISION_BLOCK


# ── result 결과 audit_required 항상 true ────────────────────────────────────


def test_result_audit_required_always_true():
    result = build_readonly_browser_result({"runtime_decision": DECISION_BLOCK})
    assert result["audit_required"] is True


# ── STEP 7 smoke: 실제 브라우저 없는 환경에서 RUNTIME_NOT_AVAILABLE 처리 ──


def test_execute_safe_to_execute_false_regardless_of_browser():
    """브라우저 설치 여부와 무관하게 safe_to_execute는 항상 False다."""
    result = execute_readonly_browser_task(
        {
            "operation_type": "read",
            "site_category": "procurement",
            "production_mode": False,
            "target_url": "data:text/html,<h1>test</h1>",
        }
    )
    assert result["safe_to_execute"] is False
    assert result["safe_to_dispatch"] is False
    # runtime_decision은 환경에 따라 다를 수 있음 - 정책 위반만 없으면 됨
    assert result["runtime_decision"] in (
        DECISION_READONLY_ALLOWED,
        DECISION_REQUIRE_USER_PRESENT,
        DECISION_RUNTIME_NOT_AVAILABLE,
        DECISION_FAILED,
        DECISION_BLOCK,
    )
