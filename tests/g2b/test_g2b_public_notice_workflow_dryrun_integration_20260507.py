"""
G2B 공개 공고 Dry-Run Workflow Integration 테스트

목적:
- evaluate_g2b_public_notice_dryrun() 검증
- dry_run=True / execution_dispatched=False 항상 유지 검증
- 허용 URL + operation → DRYRUN_READY 검증
- 차단 경로/operation → BLOCKED 검증
- 검증 필요 도메인 → NEEDS_VERIFICATION 검증
- workflow_steps에 금지 step 없음 검증
- safe_to_execute 항상 False 검증
- task_executor/browser_worker 호출 없음 정적 검사
- live 실행 코드 없음 정적 검사

금지:
- 실제 외부 사이트 접속 없음
- 브라우저/Playwright 실행 없음
- DB write 없음
- click/type/fill/submit 실행 없음
"""

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import warnings

warnings.filterwarnings("ignore")

from ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter import (  # noqa: E402 - 위 sys.path 부트스트랩 이후에만 import 가능(이동 전부터 존재)
    ADAPTER_G2B_BLOCKED,
    ADAPTER_G2B_DRYRUN_READY,
    ADAPTER_G2B_NEEDS_VERIFICATION,
    evaluate_g2b_public_notice_dryrun,
    validate_g2b_dryrun_adapter_result,
)
from ai_orchestrator.connectors.g2b.g2b_public_notice_workflow import (  # noqa: E402 - 위 sys.path 부트스트랩 이후에만 import 가능(이동 전부터 존재)
    FORBIDDEN_OPERATIONS,
    VERDICT_ALLOWED,
    VERDICT_BLOCKED,
    VERDICT_NEEDS_VERIFICATION,
)

_FORBIDDEN_STEP_NAMES = frozenset(
    {
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
)


class TestDryRunInvariants(unittest.TestCase):
    """dry_run / execution_dispatched / safe_to_execute 불변 조건."""

    _CASES = [
        ("https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read"),
        ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "open_url"),
        ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do", "navigate"),
        ("https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do", "navigate"),
        ("https://www.g2b.go.kr/cert/userCert.do", "navigate"),
        ("https://www.g2b.go.kr/pt/file/download.do", "download"),
        ("https://shop.g2b.go.kr/", "read"),
        ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "submit"),
        ("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "click"),
    ]

    def test_dry_run_always_true(self):
        for url, op in self._CASES:
            result = evaluate_g2b_public_notice_dryrun(url, operation=op)
            self.assertTrue(result["dry_run"], f"{url}+{op}: dry_run must be True")

    def test_execution_dispatched_always_false(self):
        for url, op in self._CASES:
            result = evaluate_g2b_public_notice_dryrun(url, operation=op)
            self.assertFalse(result["execution_dispatched"], f"{url}+{op}: execution_dispatched must be False")

    def test_safe_to_execute_always_false(self):
        for url, op in self._CASES:
            result = evaluate_g2b_public_notice_dryrun(url, operation=op)
            self.assertFalse(result["safe_to_execute"], f"{url}+{op}: safe_to_execute must be False")

    def test_live_browser_worker_called_always_false(self):
        for url, op in self._CASES:
            result = evaluate_g2b_public_notice_dryrun(url, operation=op)
            self.assertFalse(
                result["live_browser_worker_called"], f"{url}+{op}: live_browser_worker_called must be False"
            )

    def test_download_auto_allowed_always_false(self):
        for url, op in self._CASES:
            result = evaluate_g2b_public_notice_dryrun(url, operation=op)
            self.assertFalse(result["download_auto_allowed"], f"{url}+{op}: download_auto_allowed must be False")


class TestDryRunAllowed(unittest.TestCase):
    # A. g2b.go.kr 공개 URL read → dry_run True, execution_dispatched False, DRYRUN_READY
    def test_A_apex_read_dryrun_ready(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_DRYRUN_READY)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["execution_dispatched"])
        self.assertEqual(result["policy_verdict"], VERDICT_ALLOWED)

    # B. www.g2b.go.kr open_url → canonical/apex 정규화 확인
    def test_B_www_open_url_apex_normalized(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="open_url",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_DRYRUN_READY)
        self.assertIn("g2b.go.kr", result.get("canonical_url", ""))
        self.assertNotIn("www.g2b.go.kr", result.get("canonical_url", ""))

    # C. navigate operation → DRYRUN_READY, dry-run만 반환
    def test_C_navigate_dryrun_only(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_DRYRUN_READY)
        self.assertFalse(result["execution_dispatched"])

    # Q. PASS 결과에서도 execution_dispatched False
    def test_Q_pass_execution_dispatched_false(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb04001l.do",
            operation="read",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_DRYRUN_READY)
        self.assertFalse(result["execution_dispatched"])
        self.assertFalse(result["safe_to_execute"])

    # workflow_steps 포함 확인
    def test_allowed_has_workflow_steps(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        self.assertIsInstance(result["workflow_steps"], list)
        self.assertGreater(len(result["workflow_steps"]), 0)


class TestDryRunBlocked(unittest.TestCase):
    # D. login 경로 → BLOCKED
    def test_D_login_path_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)
        self.assertEqual(result["policy_verdict"], VERDICT_BLOCKED)

    # E. cert/sign 경로 → BLOCKED
    def test_E_cert_path_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/cert/userCert.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # F. bid/ptb05 경로 → BLOCKED
    def test_F_bid_path_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb05001p.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # G. contract/ct/menu 경로 → BLOCKED
    def test_G_contract_path_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/ct/menu/ntn02/cta01/ctb01001l.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # H. pay/payment 경로 → BLOCKED
    def test_H_payment_path_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pay/checkout.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # K. click → BLOCKED
    def test_K_click_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="click",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # L. type → BLOCKED
    def test_L_type_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="type",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # M. fill → BLOCKED
    def test_M_fill_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="fill",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # N. submit → BLOCKED
    def test_N_submit_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="submit",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    # O. download → BLOCKED, download_auto_allowed False
    def test_O_download_blocked(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/pt/file/download.do",
            operation="download",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)
        self.assertFalse(result["download_auto_allowed"])

    # P. BLOCK 결과에서 workflow_steps에 read/open_url 실행 step 없음
    def test_P_blocked_has_no_active_workflow_steps(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
            operation="navigate",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)
        # BLOCK 결과는 workflow_steps 비어 있어야 함
        self.assertEqual(result["workflow_steps"], [], "BLOCKED result should have no workflow_steps")


class TestDryRunVerification(unittest.TestCase):
    # I. shop.g2b.go.kr → NEEDS_VERIFICATION
    def test_I_shop_needs_verification(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://shop.g2b.go.kr/",
            operation="read",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_NEEDS_VERIFICATION)
        self.assertFalse(result["execution_dispatched"])
        self.assertEqual(result["policy_verdict"], VERDICT_NEEDS_VERIFICATION)

    # J. 임의 subdomain.g2b.go.kr → NEEDS_VERIFICATION
    def test_J_unknown_subdomain_needs_verification(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://subdomain.g2b.go.kr/",
            operation="read",
        )
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_NEEDS_VERIFICATION)
        self.assertFalse(result["execution_dispatched"])


class TestDryRunWorkflowStepSafety(unittest.TestCase):
    # workflow_steps에 금지 step 없음 (허용 케이스)
    def test_no_forbidden_steps_in_allowed_workflow(self):
        for op in ["read", "navigate", "open_url"]:
            result = evaluate_g2b_public_notice_dryrun(
                "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
                operation=op,
            )
            for step_entry in result.get("workflow_steps", []):
                step_name = (step_entry.get("step") or "").lower()
                self.assertNotIn(
                    step_name, _FORBIDDEN_STEP_NAMES, f"op={op}: forbidden step in workflow_steps: {step_name}"
                )

    # S. forbidden_operations가 결과에 유지됨
    def test_S_forbidden_operations_preserved(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        forbidden = result.get("forbidden_operations", [])
        for must_include in ["submit", "type", "fill", "click", "download"]:
            self.assertIn(must_include, forbidden, f"forbidden_operations must include: {must_include}")

    # allowed_operations에 금지 동작 없음
    def test_allowed_operations_no_forbidden(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        forbidden_set = set(FORBIDDEN_OPERATIONS)
        for op in result.get("allowed_operations", []):
            self.assertNotIn(op, forbidden_set, f"allowed_operations must not contain: {op}")


class TestDryRunValidation(unittest.TestCase):
    # T. validate 함수 실패 케이스
    def test_T_validate_missing_field_fails(self):
        incomplete = {"dry_run": True, "input_url": "x"}
        errors = validate_g2b_dryrun_adapter_result(incomplete)
        self.assertTrue(len(errors) > 0)

    def test_validate_safe_to_execute_true_rejected(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        result["safe_to_execute"] = True
        errors = validate_g2b_dryrun_adapter_result(result)
        self.assertTrue(any("safe_to_execute" in e for e in errors))

    def test_validate_execution_dispatched_true_rejected(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        result["execution_dispatched"] = True
        errors = validate_g2b_dryrun_adapter_result(result)
        self.assertTrue(any("execution_dispatched" in e for e in errors))

    def test_validate_valid_result_no_errors(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        errors = validate_g2b_dryrun_adapter_result(result)
        self.assertEqual(errors, [], f"유효한 결과에 에러 없어야 함: {errors}")


class TestDryRunCodeSafety(unittest.TestCase):
    """adapter / workflow 코드 정적 검사."""

    def _get_adapter_src(self):
        import ai_orchestrator.connectors.g2b.g2b_public_notice_dryrun_adapter as m

        return inspect.getsource(m)

    def _get_workflow_src(self):
        import ai_orchestrator.connectors.g2b.g2b_public_notice_workflow as m

        return inspect.getsource(m)

    # R. task_executor/browser_worker가 import/호출되지 않음
    def test_R_no_task_executor_browser_worker(self):
        src = self._get_adapter_src()
        import_lines = [
            ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        code = "\n".join(import_lines)
        self.assertNotIn("task_executor", code)
        self.assertNotIn("browser_worker", code)
        self.assertNotIn("ai_orchestrator.browser_tool.worker", code)

    def test_no_playwright_selenium_import(self):
        src = self._get_adapter_src()
        import_lines = [
            ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        code = "\n".join(import_lines)
        self.assertNotIn("playwright", code)
        self.assertNotIn("selenium", code)

    def test_no_requests_httpx_live_call(self):
        src = self._get_adapter_src()
        import_lines = [
            ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        code = "\n".join(import_lines)
        self.assertNotIn("import requests", code)
        self.assertNotIn("import httpx", code)

    def test_no_automation_calls_in_adapter(self):
        src = self._get_adapter_src()
        for call in ["page.click(", "page.type(", "page.fill(", "page.goto(", ".submit("]:
            self.assertNotIn(call, src)

    def test_no_cookie_session_token_in_adapter(self):
        src = self._get_adapter_src()
        for kw in ["page.cookies", "document.cookie", "localStorage.getItem"]:
            self.assertNotIn(kw, src)

    def test_no_db_write_in_adapter(self):
        src = self._get_adapter_src()
        for mod in ["sqlite3", "psycopg2", "sqlalchemy", "pymongo"]:
            self.assertNotIn(f"import {mod}", src)


class TestDryRunWorkflowIntegration(unittest.TestCase):
    """기존 workflow 모듈과의 통합 검증."""

    def test_adapter_uses_workflow_verdict(self):
        """adapter_decision이 workflow verdict와 일치하는지 확인."""
        result = evaluate_g2b_public_notice_dryrun(
            "https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            operation="read",
        )
        wf_verdict = result["workflow_result"].get("verdict")
        self.assertEqual(wf_verdict, VERDICT_ALLOWED)
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_DRYRUN_READY)

    def test_blocked_path_verdict_propagated(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://www.g2b.go.kr/co/menu/EgovUserReqstLogin.do",
            operation="navigate",
        )
        wf_verdict = result["workflow_result"].get("verdict")
        self.assertEqual(wf_verdict, VERDICT_BLOCKED)
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_BLOCKED)

    def test_verification_verdict_propagated(self):
        result = evaluate_g2b_public_notice_dryrun(
            "https://shop.g2b.go.kr/",
            operation="read",
        )
        wf_verdict = result["workflow_result"].get("verdict")
        self.assertEqual(wf_verdict, VERDICT_NEEDS_VERIFICATION)
        self.assertEqual(result["adapter_decision"], ADAPTER_G2B_NEEDS_VERIFICATION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
