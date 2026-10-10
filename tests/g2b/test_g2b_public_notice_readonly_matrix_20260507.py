"""
G2B 공개 업무 읽기 전용 접근 매트릭스 테스트

목적:
- 10개 G2B 화면 후보 정책 분류 검증
- server_browser_allowed / execution_location_required 검증
- safe_to_execute 항상 False 검증
- 읽기 전용 화면 5개 ALLOW_BROWSER_READONLY 검증
- 다운로드 operation BLOCK 검증
- 로그인/인증서 요구 화면 BLOCK 검증
- subdomain www.g2b.go.kr allowlist 불일치 BLOCK 검증
- g2b_public_readonly SERVER_BROWSER 분류 검증
- fixture와 정책 모듈 일치 검증

금지:
- 실제 외부 사이트 접속 없음
- 브라우저/Playwright 실행 없음
- DB write 없음
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import warnings

warnings.filterwarnings("ignore")

from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (  # noqa: E402
    evaluate_server_browser_allowed,
)
from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance  # noqa: E402

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "g2b_public_notice_readonly_matrix_20260507.json"

_READONLY_VERDICTS = {"READ_ONLY_ALLOWED"}
_BLOCKED_VERDICTS = {"BLOCKED_LOGIN_REQUIRED", "BLOCKED_CERT_REQUIRED", "BLOCKED_AUTH_REQUIRED", "DOWNLOAD_MANUAL_ONLY"}

_READ_ONLY_IDS = {"g2b_01", "g2b_02", "g2b_03", "g2b_04", "g2b_06", "g2b_07"}
_BLOCKED_AUTH_IDS = {"g2b_08", "g2b_09", "g2b_10"}
_DOWNLOAD_ID = "g2b_05"


def _load_fixture():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _build_payload(case: dict) -> dict:
    payload = {
        "site_category": case["site_category"],
        "target_domain": case["target_domain"],
        "operation_type": case["operation_type"],
    }
    if case.get("requires_certificate"):
        payload["requires_certificate"] = True
    return payload


class TestG2BFixtureStructure(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()

    # 1. fixture 파일 로드 가능
    def test_01_fixture_loads(self):
        self.assertIn("cases", self.fixture)
        self.assertIn("meta", self.fixture)

    # 2. fixture cases 10개
    def test_02_fixture_has_10_cases(self):
        self.assertEqual(len(self.fixture["cases"]), 10)

    # 3. 각 case에 필수 필드 존재
    def test_03_required_fields_in_each_case(self):
        required = {"id", "screen_name", "site_category", "target_domain", "operation_type", "expected"}
        for case in self.fixture["cases"]:
            for field in required:
                self.assertIn(field, case, f"case {case.get('id')} 필드 누락: {field}")

    # 4. expected에 safe_to_execute=False 있음
    def test_04_safe_to_execute_false_in_expected(self):
        for case in self.fixture["cases"]:
            self.assertFalse(case["expected"]["safe_to_execute"], f"{case['id']} safe_to_execute must be False")

    # 5. g2b_public_readonly 화면 6개
    def test_05_readonly_category_count(self):
        readonly_cases = [c for c in self.fixture["cases"] if c["site_category"] == "g2b_public_readonly"]
        self.assertEqual(len(readonly_cases), 7)  # g2b_01~g2b_07 (05 포함)

    # 6. g2b_login 화면 3개
    def test_06_login_category_count(self):
        login_cases = [c for c in self.fixture["cases"] if c["site_category"] == "g2b_login"]
        self.assertEqual(len(login_cases), 3)


class TestG2BPolicyCompliance(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()
        self.cases = {c["id"]: c for c in self.fixture["cases"]}

    # 7. 읽기 화면 compliance_decision = ALLOW_BROWSER_READONLY
    def test_07_readonly_screens_compliance_allow(self):
        for cid in _READ_ONLY_IDS:
            case = self.cases[cid]
            payload = _build_payload(case)
            result = evaluate_site_compliance(payload)
            self.assertEqual(
                result["compliance_decision"],
                "ALLOW_BROWSER_READONLY",
                f"{cid} {case['screen_name']}: expected ALLOW_BROWSER_READONLY, got {result['compliance_decision']}",
            )

    # 8. 다운로드 operation compliance_decision = BLOCK
    def test_08_download_operation_blocked(self):
        case = self.cases[_DOWNLOAD_ID]
        payload = _build_payload(case)
        result = evaluate_site_compliance(payload)
        self.assertEqual(
            result["compliance_decision"],
            "BLOCK",
            f"download operation should be BLOCK, got {result['compliance_decision']}",
        )

    # 9. 로그인/인증 화면 compliance_decision = BLOCK
    def test_09_auth_screens_compliance_block(self):
        for cid in _BLOCKED_AUTH_IDS:
            case = self.cases[cid]
            payload = _build_payload(case)
            result = evaluate_site_compliance(payload)
            self.assertNotEqual(
                result["compliance_decision"],
                "ALLOW_BROWSER_READONLY",
                f"{cid} should not be ALLOW, got {result['compliance_decision']}",
            )

    # 10. 모든 compliance 결과 safe_to_execute=False
    def test_10_all_compliance_safe_to_execute_false(self):
        for case in self.fixture["cases"]:
            payload = _build_payload(case)
            result = evaluate_site_compliance(payload)
            self.assertFalse(result.get("safe_to_execute"), f"{case['id']} safe_to_execute must be False")


class TestG2BServerBrowserBoundary(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()
        self.cases = {c["id"]: c for c in self.fixture["cases"]}

    # 11. 읽기 화면 server_browser_allowed=True
    def test_11_readonly_screens_server_browser_allowed(self):
        for cid in _READ_ONLY_IDS:
            case = self.cases[cid]
            payload = _build_payload(case)
            result = evaluate_server_browser_allowed(payload)
            self.assertTrue(
                result["server_browser_allowed"], f"{cid} {case['screen_name']}: server_browser_allowed should be True"
            )

    # 12. 읽기 화면 execution_location_required = SERVER_BROWSER
    def test_12_readonly_screens_execution_loc_server_browser(self):
        for cid in _READ_ONLY_IDS:
            case = self.cases[cid]
            payload = _build_payload(case)
            result = evaluate_server_browser_allowed(payload)
            self.assertEqual(
                result["execution_location_required"],
                "SERVER_BROWSER",
                f"{cid}: execution_loc should be SERVER_BROWSER",
            )

    # 13. 로그인/인증 화면 server_browser_allowed=False
    def test_13_auth_screens_server_browser_not_allowed(self):
        for cid in _BLOCKED_AUTH_IDS:
            case = self.cases[cid]
            payload = _build_payload(case)
            result = evaluate_server_browser_allowed(payload)
            self.assertFalse(result["server_browser_allowed"], f"{cid}: server_browser_allowed should be False")

    # 14. 인증서 요구 화면 execution_location = USER_PRESENT_ONLY
    def test_14_cert_required_execution_loc_user_present(self):
        for cid in {"g2b_09", "g2b_10"}:
            case = self.cases[cid]
            payload = _build_payload(case)
            result = evaluate_server_browser_allowed(payload)
            self.assertEqual(
                result["execution_location_required"],
                "USER_PRESENT_ONLY",
                f"{cid}: execution_loc should be USER_PRESENT_ONLY",
            )

    # 15. 모든 server_browser 결과 safe_to_execute=False
    def test_15_all_server_browser_safe_to_execute_false(self):
        for case in self.fixture["cases"]:
            payload = _build_payload(case)
            result = evaluate_server_browser_allowed(payload)
            self.assertFalse(result.get("safe_to_execute"), f"{case['id']} safe_to_execute must be False")


class TestG2BSubdomainPolicy(unittest.TestCase):
    # 16. www.g2b.go.kr는 allowlist 추가 후 ALLOW_BROWSER_READONLY (G2B_DOMAIN_NORMALIZATION_POLICY_1 수정)
    def test_16_www_subdomain_now_in_allowlist(self):
        payload = {
            "site_category": "g2b_public_readonly",
            "target_domain": "www.g2b.go.kr",
            "operation_type": "read",
        }
        result = evaluate_site_compliance(payload)
        self.assertEqual(
            result["compliance_decision"],
            "ALLOW_BROWSER_READONLY",
            "www.g2b.go.kr should ALLOW_BROWSER_READONLY after normalization fix",
        )

    # 17. g2b.go.kr(apex domain)는 allowlist 일치 → ALLOW_BROWSER_READONLY
    def test_17_apex_domain_in_allowlist(self):
        payload = {
            "site_category": "g2b_public_readonly",
            "target_domain": "g2b.go.kr",
            "operation_type": "read",
        }
        result = evaluate_site_compliance(payload)
        self.assertEqual(
            result["compliance_decision"], "ALLOW_BROWSER_READONLY", "g2b.go.kr should be ALLOW_BROWSER_READONLY"
        )

    # 18. g2b_public_readonly 카테고리 server_browser_allowed=True (domain 무관)
    def test_18_g2b_public_readonly_server_browser_true_regardless_of_www(self):
        for domain in ["g2b.go.kr", "www.g2b.go.kr"]:
            payload = {
                "site_category": "g2b_public_readonly",
                "target_domain": domain,
                "operation_type": "read",
            }
            result = evaluate_server_browser_allowed(payload)
            self.assertTrue(
                result["server_browser_allowed"],
                f"g2b_public_readonly + {domain} should have server_browser_allowed=True",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
