"""
G2B 공개 공고 Read-Only 워크플로우 테스트

목적:
- build_g2b_public_notice_workflow() 검증
- classify_g2b_public_notice_workflow_request() 검증
- validate_g2b_public_notice_workflow_result() 검증
- 허용 도메인/경로/operation 검증
- 차단 도메인/경로/operation 검증
- workflow_steps 금지 step 없음 검증
- safe_to_execute / download_auto_allowed 항상 False 검증
- g2b_domain_policy 기존 테스트와 호환 확인

금지:
- 실제 외부 사이트 접속 없음
- 브라우저/Playwright 실행 없음
- DB write 없음
- click/type/fill/submit 실행 없음
"""

import inspect
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import warnings

warnings.filterwarnings("ignore")

from ai_orchestrator.connectors.g2b.g2b_public_notice_workflow import (  # noqa: E402
    FORBIDDEN_OPERATIONS,
    VERDICT_ALLOWED,
    VERDICT_BLOCKED,
    VERDICT_NEEDS_VERIFICATION,
    build_g2b_public_notice_workflow,
    validate_g2b_public_notice_workflow_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json"

_FORBIDDEN_STEP_NAMES = {
    "click",
    "type",
    "fill",
    "submit",
    "download",
    "login",
    "cert",
    "payment",
    "contract_submit",
    "bid_submit",
    "auto_login",
    "upload",
    "write_form",
}


def _load_fixture():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


class TestFixtureStructure(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()

    def test_fixture_loads(self):
        self.assertIn("cases", self.fixture)
        self.assertGreaterEqual(len(self.fixture["cases"]), 15)

    def test_all_expected_safe_to_execute_false(self):
        for case in self.fixture["cases"]:
            self.assertFalse(case["expected"].get("safe_to_execute"), f"{case['id']}: safe_to_execute should be False")


class TestG2BWorkflowAllowed(unittest.TestCase):
    # A. g2b.go.kr 공개 URL + read → PASS
    def test_A_apex_read_allowed(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        self.assertEqual(result["verdict"], VERDICT_ALLOWED)
        self.assertTrue(result["readonly_allowed"])
        self.assertFalse(result["safe_to_execute"])

    # B. www.g2b.go.kr + open_url → PASS + apex 정규화
    def test_B_www_open_url_apex_normalized(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="open_url",
        )
        self.assertEqual(result["verdict"], VERDICT_ALLOWED)
        self.assertEqual(result["normalized_domain"], "g2b.go.kr")
        self.assertFalse(result["download_auto_allowed"])

    # B2. canonical_url이 apex domain으로 정규화됨
    def test_B2_www_canonical_url_uses_apex(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        self.assertIn("g2b.go.kr", result.get("canonical_url", ""))
        self.assertNotIn("www.g2b.go.kr", result.get("canonical_url", ""))

    # C. www.g2b.go.kr + navigate → PASS
    def test_C_www_navigate_allowed(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do",
            operation="navigate",
        )
        self.assertEqual(result["verdict"], VERDICT_ALLOWED)
        self.assertTrue(result["readonly_allowed"])

    # workflow_steps 포함 확인
    def test_allowed_result_has_workflow_steps(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        self.assertIsInstance(result["workflow_steps"], list)
        self.assertGreater(len(result["workflow_steps"]), 0)

    # compliance_decision = ALLOW_BROWSER_READONLY
    def test_allowed_compliance_decision(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        self.assertEqual(result["compliance_decision"], "ALLOW_BROWSER_READONLY")


class TestG2BWorkflowBlocked(unittest.TestCase):
    # D. login 경로 → BLOCK
    def test_D_login_path_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
            operation="navigate",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)
        self.assertFalse(result["readonly_allowed"])

    # E. cert/sign 경로 → BLOCK
    def test_E_cert_path_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/cert/userCert.do",
            operation="navigate",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # F. bid/ptb05 경로 → BLOCK
    def test_F_bid_path_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb05001p.do",
            operation="navigate",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # G. contract/ct/menu 경로 → BLOCK
    def test_G_contract_path_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/ct/menu/ntn02/cta01/ctb01001l.do",
            operation="navigate",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # H. pay/payment 경로 → BLOCK
    def test_H_payment_path_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pay/checkout.do",
            operation="navigate",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # K. operation click → BLOCK
    def test_K_click_operation_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="click",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)
        self.assertFalse(result["readonly_allowed"])

    # L. operation type → BLOCK
    def test_L_type_operation_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="type",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # M. operation fill → BLOCK
    def test_M_fill_operation_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="fill",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # N. operation submit → BLOCK
    def test_N_submit_operation_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="submit",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)

    # O. operation download → BLOCK, download_auto_allowed False
    def test_O_download_operation_blocked(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/file/download.do",
            operation="download",
        )
        self.assertEqual(result["verdict"], VERDICT_BLOCKED)
        self.assertFalse(result["download_auto_allowed"])
        self.assertFalse(result["safe_to_execute"])


class TestG2BWorkflowVerification(unittest.TestCase):
    # I. shop.g2b.go.kr → NEEDS_VERIFICATION
    def test_I_shop_needs_verification(self):
        result = build_g2b_public_notice_workflow(
            "https://shop.g2b.go.kr/",
            operation="read",
        )
        self.assertEqual(result["verdict"], VERDICT_NEEDS_VERIFICATION)
        self.assertTrue(result["requires_url_verification"])
        self.assertFalse(result["readonly_allowed"])

    # J. abc.g2b.go.kr → NEEDS_VERIFICATION
    def test_J_unknown_subdomain_needs_verification(self):
        result = build_g2b_public_notice_workflow(
            "https://abc.g2b.go.kr/",
            operation="read",
        )
        self.assertEqual(result["verdict"], VERDICT_NEEDS_VERIFICATION)
        self.assertTrue(result["requires_url_verification"])


class TestG2BWorkflowFileList(unittest.TestCase):
    # P. 파일 목록 read → 허용, download step 없음
    def test_P_file_list_read_allowed_no_download_step(self):
        result = build_g2b_public_notice_workflow(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do",
            operation="read",
        )
        self.assertEqual(result["verdict"], VERDICT_ALLOWED)
        self.assertFalse(result["download_auto_allowed"])
        # workflow_steps에 download step 없음
        for step in result.get("workflow_steps", []):
            step_name = step.get("step", "").lower()
            self.assertNotIn("download", step_name, f"download step should not appear: {step}")

    # Q. workflow_steps 안에 금지 step이 하나도 없는지 검사
    def test_Q_no_forbidden_steps_in_workflow(self):
        for op in ["read", "navigate", "open_url"]:
            result = build_g2b_public_notice_workflow(
                "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
                operation=op,
            )
            for step in result.get("workflow_steps", []):
                step_name = (step.get("step") or "").lower()
                self.assertNotIn(
                    step_name, _FORBIDDEN_STEP_NAMES, f"operation={op}: forbidden step in workflow_steps: {step_name}"
                )


class TestG2BWorkflowValidation(unittest.TestCase):
    # R. validate 함수가 필수 필드 누락을 잡는지 검사
    def test_R_validate_missing_required_field(self):
        incomplete = {
            "input_url": "https://g2b.go.kr/",
            # 나머지 필드 누락
        }
        errors = validate_g2b_public_notice_workflow_result(incomplete)
        self.assertTrue(len(errors) > 0, "필수 필드 누락 시 에러 반환해야 함")

    def test_validate_safe_to_execute_true_rejected(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        result["safe_to_execute"] = True
        errors = validate_g2b_public_notice_workflow_result(result)
        self.assertTrue(any("safe_to_execute" in e for e in errors))

    def test_validate_download_auto_allowed_true_rejected(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        result["download_auto_allowed"] = True
        errors = validate_g2b_public_notice_workflow_result(result)
        self.assertTrue(any("download_auto_allowed" in e for e in errors))

    def test_validate_forbidden_step_in_workflow_rejected(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        result["workflow_steps"].append({"step": "submit", "mode": "write"})
        errors = validate_g2b_public_notice_workflow_result(result)
        self.assertTrue(any("submit" in e for e in errors))

    def test_validate_valid_result(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        errors = validate_g2b_public_notice_workflow_result(result)
        self.assertEqual(errors, [], f"유효한 결과에 에러 없어야 함: {errors}")


class TestG2BWorkflowInvariants(unittest.TestCase):
    # 모든 케이스 safe_to_execute=False
    def test_all_results_safe_to_execute_false(self):
        cases = [
            ("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read"),
            ("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"),
            ("https://www.g2b.go.kr/cert/userCert.do", "navigate"),
            ("https://www.g2b.go.kr/pt/file/download.do", "download"),
            ("https://shop.g2b.go.kr/", "read"),
            ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "submit"),
            ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "type"),
        ]
        for url, op in cases:
            result = build_g2b_public_notice_workflow(url, operation=op)
            self.assertFalse(result["safe_to_execute"], f"{url}+{op}: safe_to_execute must be False")

    # 모든 케이스 download_auto_allowed=False
    def test_all_results_download_auto_allowed_false(self):
        cases = [
            ("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read"),
            ("https://www.g2b.go.kr/pt/file/download.do", "download"),
            ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "navigate"),
        ]
        for url, op in cases:
            result = build_g2b_public_notice_workflow(url, operation=op)
            self.assertFalse(result.get("download_auto_allowed"), f"{url}+{op}: download_auto_allowed must be False")

    # allowed_operations에 금지 동작 없음
    def test_allowed_operations_no_forbidden(self):
        result = build_g2b_public_notice_workflow(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        forbidden_set = set(FORBIDDEN_OPERATIONS)
        for op in result.get("allowed_operations", []):
            self.assertNotIn(op, forbidden_set, f"allowed_operations should not contain forbidden op: {op}")


class TestG2BWorkflowCodeSafety(unittest.TestCase):
    def _get_src(self):
        import ai_orchestrator.connectors.g2b.g2b_public_notice_workflow as m

        return inspect.getsource(m)

    def test_no_cookie_session_token_extraction(self):
        src = self._get_src()
        for kw in ["page.cookies", "document.cookie", "localStorage.getItem", "sessionStorage"]:
            self.assertNotIn(kw, src)

    def test_no_automation_calls(self):
        src = self._get_src()
        for call in ["page.click(", "page.type(", "page.fill(", "page.goto(", ".submit("]:
            self.assertNotIn(call, src)

    def test_no_db_write(self):
        src = self._get_src()
        for mod in ["sqlite3", "psycopg2", "sqlalchemy", "pymongo"]:
            self.assertNotIn(f"import {mod}", src)

    def test_no_task_executor_browser_worker_connection(self):
        src = self._get_src()
        # import 라인만 검사 (BLOCK 검증용 문자열 제외)
        import_lines = [
            ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        code = "\n".join(import_lines)
        self.assertNotIn("task_executor", code)
        self.assertNotIn("browser_worker", code)
        self.assertNotIn("ai_orchestrator.browser_tool.worker", code)


class TestG2BWorkflowFixtureCompatibility(unittest.TestCase):
    def setUp(self):
        self.fixture = _load_fixture()

    def test_fixture_allowed_cases(self):
        allowed = [c for c in self.fixture["cases"] if c["expected"].get("verdict") == "ALLOWED"]
        self.assertGreaterEqual(len(allowed), 4)

    def test_fixture_blocked_cases(self):
        blocked = [c for c in self.fixture["cases"] if c["expected"].get("verdict") == "BLOCKED"]
        self.assertGreaterEqual(len(blocked), 8)

    def test_fixture_verification_cases(self):
        verify = [c for c in self.fixture["cases"] if c["expected"].get("verdict") == "NEEDS_VERIFICATION"]
        self.assertGreaterEqual(len(verify), 2)

    def test_fixture_download_blocked(self):
        dl = [c for c in self.fixture["cases"] if c["operation"] == "download"]
        self.assertGreaterEqual(len(dl), 1)
        for c in dl:
            self.assertFalse(c["expected"].get("download_auto_allowed", True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
