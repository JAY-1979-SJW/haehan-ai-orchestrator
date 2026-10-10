"""
G2B 도메인 정규화 정책 테스트

목적:
- apex/www 도메인 정규화 검증
- 공개 read-only 경로 허용 검증
- login/cert/bid/submit/contract/payment 경로 차단 검증
- operation 차단 검증
- safe_to_execute / download_auto_allowed 항상 False 검증
- allowlist_preflight / routing_policy 호환 검증
- wildcard 허용 없음 검증
- 쿠키/session/token 코드 없음 검증
- 자동 click/type/fill/submit 코드 없음 검증
- DB write 없음 검증

금지:
- 실제 외부 사이트 접속 없음
- 브라우저/Playwright 실행 없음
- DB write 없음
"""

import inspect
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import warnings

warnings.filterwarnings("ignore")

from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance  # noqa: E402
from ai_orchestrator.browser_tool.preflight.allowlist_preflight import evaluate_allowlist_preflight  # noqa: E402
from ai_orchestrator.connectors.g2b.g2b_domain_policy import (  # noqa: E402
    DOMAIN_G2B_PUBLIC_READONLY,
    DOMAIN_NEEDS_URL_VERIFICATION,
    DOMAIN_READONLY_CANDIDATE,
    PATH_BLOCKED_BID_SUBMIT,
    PATH_BLOCKED_CERT,
    PATH_BLOCKED_CONTRACT,
    PATH_BLOCKED_LOGIN,
    PATH_BLOCKED_PAYMENT,
    PATH_READONLY_ALLOWED,
    classify_g2b_url,
    is_g2b_readonly_allowed,
    normalize_g2b_domain,
    validate_g2b_domain_policy_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "g2b_domain_normalization_policy_20260507.json"


def _load_fixture():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


class TestFixtureStructure(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()

    # 1. fixture JSON 로드 가능
    def test_01_fixture_loads(self):
        self.assertIn("cases", self.fixture)
        self.assertEqual(len(self.fixture["cases"]), 16)

    # 2. 모든 케이스에 safe_to_execute=False 기대값
    def test_02_all_expected_safe_to_execute_false(self):
        for case in self.fixture["cases"]:
            self.assertFalse(case["expected"].get("safe_to_execute"), f"{case['id']}: safe_to_execute should be False")


class TestG2BDomainNormalization(unittest.TestCase):
    # 2. g2b.go.kr 공개 read-only 후보
    def test_02_apex_domain_g2b_public_readonly(self):
        result = normalize_g2b_domain("g2b.go.kr")
        self.assertEqual(result["domain_decision"], DOMAIN_G2B_PUBLIC_READONLY)
        self.assertTrue(result["is_g2b_public_readonly"])
        self.assertFalse(result["safe_to_execute"])

    # 3. www.g2b.go.kr 공개 read-only 후보
    def test_03_www_domain_g2b_public_readonly(self):
        result = normalize_g2b_domain("www.g2b.go.kr")
        self.assertEqual(result["domain_decision"], DOMAIN_G2B_PUBLIC_READONLY)
        self.assertTrue(result["is_g2b_public_readonly"])

    # 4. www.g2b.go.kr → g2b.go.kr 정규화
    def test_04_www_normalizes_to_apex(self):
        result = normalize_g2b_domain("www.g2b.go.kr")
        self.assertEqual(result["normalized_domain"], "g2b.go.kr")

    # 5. shop.g2b.go.kr는 READONLY_CANDIDATE
    def test_05_shop_subdomain_readonly_candidate(self):
        result = normalize_g2b_domain("shop.g2b.go.kr")
        self.assertEqual(result["domain_decision"], DOMAIN_READONLY_CANDIDATE)
        self.assertTrue(result["needs_url_verification"])
        self.assertFalse(result["is_g2b_public_readonly"])

    # 6. 미확인 서브도메인 NEEDS_URL_VERIFICATION
    def test_06_unknown_subdomain_needs_verification(self):
        result = normalize_g2b_domain("api.g2b.go.kr")
        self.assertEqual(result["domain_decision"], DOMAIN_NEEDS_URL_VERIFICATION)
        self.assertTrue(result["needs_url_verification"])

    # 22. wildcard 허용 없음 - 미확인 서브도메인은 공개 read-only 아님
    def test_22_no_wildcard_g2b_subdomains_allowed(self):
        for sub in ["secure.g2b.go.kr", "admin.g2b.go.kr", "test.g2b.go.kr", "internal.g2b.go.kr"]:
            result = normalize_g2b_domain(sub)
            self.assertFalse(result["is_g2b_public_readonly"], f"{sub} should not be public readonly (no wildcard)")
            self.assertNotEqual(
                result["domain_decision"], DOMAIN_G2B_PUBLIC_READONLY, f"{sub} should not be G2B_PUBLIC_READONLY"
            )


class TestG2BUrlClassification(unittest.TestCase):
    # 7. login path BLOCK
    def test_07_login_path_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
            operation_type="navigate",
        )
        self.assertEqual(result["path_decision"], PATH_BLOCKED_LOGIN)
        self.assertFalse(result["readonly_allowed"])
        self.assertFalse(result["safe_to_execute"])

    # 8. certificate path BLOCK
    def test_08_cert_path_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/cert/userCert.do",
            operation_type="navigate",
        )
        self.assertEqual(result["path_decision"], PATH_BLOCKED_CERT)
        self.assertFalse(result["readonly_allowed"])

    # 9. bid/submit path BLOCK
    def test_09_bid_submit_path_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb05001p.do",
            operation_type="navigate",
        )
        self.assertEqual(result["path_decision"], PATH_BLOCKED_BID_SUBMIT)
        self.assertFalse(result["readonly_allowed"])

    # 10. contract path BLOCK
    def test_10_contract_path_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/ct/menu/ntn02/cta01/ctb01001l.do",
            operation_type="navigate",
        )
        self.assertEqual(result["path_decision"], PATH_BLOCKED_CONTRACT)
        self.assertFalse(result["readonly_allowed"])

    # 11. payment path BLOCK
    def test_11_payment_path_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pay/checkout.do",
            operation_type="navigate",
        )
        self.assertEqual(result["path_decision"], PATH_BLOCKED_PAYMENT)
        self.assertFalse(result["readonly_allowed"])

    # 12. attachment list는 DOWNLOAD_MANUAL_ONLY (read operation은 허용, download는 차단)
    def test_12_attachment_list_read_allowed(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do",
            operation_type="read",
        )
        self.assertEqual(result["path_decision"], PATH_READONLY_ALLOWED)
        self.assertTrue(result["readonly_allowed"])
        self.assertFalse(result["download_auto_allowed"])

    # 13. attachment auto download BLOCK
    def test_13_attachment_auto_download_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pt/file/download.do",
            operation_type="download",
        )
        self.assertEqual(result["operation_decision"], "BLOCKED")
        self.assertFalse(result["download_auto_allowed"])
        self.assertFalse(result["safe_to_execute"])

    # 14. type operation BLOCK
    def test_14_type_operation_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation_type="type",
        )
        self.assertEqual(result["operation_decision"], "BLOCKED")
        self.assertFalse(result["readonly_allowed"])

    # 15. submit operation BLOCK
    def test_15_submit_operation_blocked(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation_type="submit",
        )
        self.assertEqual(result["operation_decision"], "BLOCKED")
        self.assertFalse(result["readonly_allowed"])

    # 16. click operation은 별도 승인 필요
    def test_16_click_operation_requires_approval(self):
        result = classify_g2b_url(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation_type="click",
        )
        self.assertEqual(result["operation_decision"], "REQUIRES_APPROVAL")
        self.assertTrue(result["requires_approval"])
        self.assertFalse(result["safe_to_execute"])

    # 17. safe_to_execute는 모든 케이스 false
    def test_17_all_results_safe_to_execute_false(self):
        test_cases = [
            ("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read"),
            ("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"),
            ("https://www.g2b.go.kr/cert/userCert.do", "navigate"),
            ("https://www.g2b.go.kr/pt/file/download.do", "download"),
            ("https://shop.g2b.go.kr/", "read"),
        ]
        for url, op in test_cases:
            result = classify_g2b_url(url, operation_type=op)
            self.assertFalse(result["safe_to_execute"], f"{url} + {op}: safe_to_execute must be False")

    def test_17b_all_download_auto_allowed_false(self):
        test_cases = [
            ("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read"),
            ("https://www.g2b.go.kr/pt/file/download.do", "download"),
        ]
        for url, op in test_cases:
            result = classify_g2b_url(url, operation_type=op)
            self.assertFalse(result.get("download_auto_allowed"), f"{url}: download_auto_allowed must be False")


class TestG2BIsReadonlyAllowed(unittest.TestCase):
    def test_is_g2b_readonly_allowed_apex(self):
        self.assertTrue(is_g2b_readonly_allowed("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do"))

    def test_is_g2b_readonly_allowed_www(self):
        self.assertTrue(is_g2b_readonly_allowed("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do"))

    def test_is_g2b_readonly_not_allowed_login(self):
        self.assertFalse(is_g2b_readonly_allowed("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do"))


class TestG2BCompatibility(unittest.TestCase):
    # 18. allowlist_preflight와 호환 — www.g2b.go.kr이 ALLOW_DRY_RUN 반환
    def test_18_allowlist_preflight_www_allowed(self):
        payload = {
            "action_name": "g2b_test",
            "operation_type": "navigate",
            "target_domain": "www.g2b.go.kr",
            "tenant_id": "haehan",
        }
        result = evaluate_allowlist_preflight(payload)
        self.assertNotEqual(
            result["allowlist_decision"],
            "BLOCK",
            f"www.g2b.go.kr should not be BLOCK in allowlist, got {result['allowlist_decision']}",
        )

    # 19. routing_policy와 호환 — g2b.go.kr와 www 모두 동일 분류
    def test_19_site_compliance_www_allow(self):
        for domain in ["g2b.go.kr", "www.g2b.go.kr"]:
            payload = {
                "target_domain": domain,
                "operation_type": "read",
                "site_category": "g2b_public_readonly",
            }
            result = evaluate_site_compliance(payload)
            self.assertEqual(
                result["compliance_decision"],
                "ALLOW_BROWSER_READONLY",
                f"{domain} should be ALLOW_BROWSER_READONLY, got {result['compliance_decision']}",
            )

    # 20. server_boundary_policy와 호환 — g2b_public_readonly server_allowed=True
    def test_20_server_boundary_g2b_public_readonly(self):
        from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import evaluate_server_browser_allowed

        for domain in ["g2b.go.kr", "www.g2b.go.kr"]:
            payload = {
                "site_category": "g2b_public_readonly",
                "target_domain": domain,
                "operation_type": "read",
            }
            result = evaluate_server_browser_allowed(payload)
            self.assertTrue(result["server_browser_allowed"], f"{domain}: server_browser_allowed should be True")

    # 21. G2B matrix와 호환 — 기존 6개 READ_ONLY_ALLOWED 케이스 유지
    def test_21_g2b_matrix_readonly_still_allowed(self):
        from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance

        for domain in ["g2b.go.kr", "www.g2b.go.kr"]:
            for op in ["read", "navigate"]:
                payload = {
                    "site_category": "g2b_public_readonly",
                    "target_domain": domain,
                    "operation_type": op,
                }
                result = evaluate_site_compliance(payload)
                self.assertEqual(
                    result["compliance_decision"],
                    "ALLOW_BROWSER_READONLY",
                    f"{domain}+{op}: expected ALLOW_BROWSER_READONLY",
                )


class TestG2BCodeSafety(unittest.TestCase):
    # 23. 쿠키/session/token 추출 코드 없음
    def test_23_no_cookie_session_token_extraction(self):
        import ai_orchestrator.connectors.g2b.g2b_domain_policy as m

        src = inspect.getsource(m)
        forbidden = [
            "page.cookies",
            "page.context.cookies",
            "localStorage.getItem",
            "sessionStorage.getItem",
            "document.cookie",
        ]
        for kw in forbidden:
            self.assertNotIn(kw, src, f"g2b_domain_policy should not contain: {kw}")

    # 24. 자동 click/type/fill/submit 코드 없음
    def test_24_no_automation_calls(self):
        import ai_orchestrator.connectors.g2b.g2b_domain_policy as m

        src = inspect.getsource(m)
        for call in ["page.click(", "page.type(", "page.fill(", "page.goto(", ".submit("]:
            self.assertNotIn(call, src, f"g2b_domain_policy should not contain: {call}")

    # 25. DB write 없음
    def test_25_no_db_write(self):
        import ai_orchestrator.connectors.g2b.g2b_domain_policy as m

        src = inspect.getsource(m)
        for mod in ["sqlite3", "psycopg2", "sqlalchemy", "pymongo"]:
            self.assertNotIn(f"import {mod}", src, f"{mod} found in g2b_domain_policy")


class TestG2BValidate(unittest.TestCase):
    def test_validate_valid_result(self):
        record = {
            "domain_decision": "G2B_PUBLIC_READONLY",
            "path_decision": "PATH_READONLY_ALLOWED",
            "readonly_allowed": True,
            "download_auto_allowed": False,
            "safe_to_execute": False,
        }
        errors = validate_g2b_domain_policy_result(record)
        self.assertEqual(errors, [])

    def test_validate_rejects_safe_to_execute_true(self):
        record = {
            "domain_decision": "G2B_PUBLIC_READONLY",
            "path_decision": "PATH_READONLY_ALLOWED",
            "readonly_allowed": True,
            "download_auto_allowed": False,
            "safe_to_execute": True,
        }
        errors = validate_g2b_domain_policy_result(record)
        self.assertTrue(any("safe_to_execute" in e for e in errors))

    def test_validate_rejects_download_auto_allowed_true(self):
        record = {
            "domain_decision": "G2B_PUBLIC_READONLY",
            "path_decision": "PATH_READONLY_ALLOWED",
            "readonly_allowed": True,
            "download_auto_allowed": True,
            "safe_to_execute": False,
        }
        errors = validate_g2b_domain_policy_result(record)
        self.assertTrue(any("download_auto_allowed" in e for e in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
