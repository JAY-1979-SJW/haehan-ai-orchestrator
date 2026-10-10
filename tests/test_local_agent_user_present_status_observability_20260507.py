"""
USER_PRESENT_STATUS Observability 테스트

목적:
- status store 저장/조회 검증
- handler audit log + store 연결 검증
- 민감정보 저장 금지
- safe_to_execute=true reject
- 조회 API 구조 검증
- 기존 handler 호환 검증

금지:
- 실제 외부 사이트 접속 없음
- 브라우저/Playwright 실행 없음
- click/type/fill/submit 없음
- DB write 없음
- browser_worker/task_executor 호출 없음
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_orchestrator.agent_hub.user_present_status_handler import (
    clear_status_registry,
    handle_user_present_status_event,
)
from ai_orchestrator.agent_hub.user_present_status_handler import (
    get_user_present_status as handler_get_status,
)
from ai_orchestrator.agent_hub.user_present_status_store import (
    clear_store_for_testing,
    get_user_present_status,
    list_user_present_statuses,
    record_user_present_status,
    validate_stored_user_present_status,
)


def _base_event(wf_id: str, status: str = "USER_CONFIRMED") -> dict:
    return {
        "message_type": "USER_PRESENT_STATUS",
        "workflow_run_id": wf_id,
        "tenant_id": "haehan",
        "user_id": "testuser",
        "site_id": "g2b",
        "status": status,
        "status_reason": "",
        "safe_to_execute": False,
        "created_at": "2026-05-07T12:00:00+00:00",
    }


class TestStatusStore(unittest.TestCase):
    def setUp(self):
        clear_store_for_testing()
        clear_status_registry()

    # 1. USER_CONFIRMED 저장
    def test_01_record_user_confirmed(self):
        ev = _base_event("wf_obs_01", "USER_CONFIRMED")
        result = record_user_present_status(ev, agent_id="la-test-01")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "USER_CONFIRMED")
        self.assertIn("received_at", result)
        self.assertFalse(result["safe_to_execute"])

    # 2. CANCELLED 저장
    def test_02_record_cancelled(self):
        ev = _base_event("wf_obs_02", "CANCELLED")
        result = record_user_present_status(ev, agent_id="la-test-01")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "CANCELLED")

    # 3. BLOCKED 저장
    def test_03_record_blocked(self):
        ev = _base_event("wf_obs_03", "BLOCKED")
        result = record_user_present_status(ev, agent_id="la-test-01")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "BLOCKED")

    # 4. FAILED 저장
    def test_04_record_failed(self):
        ev = _base_event("wf_obs_04", "FAILED")
        result = record_user_present_status(ev, agent_id="la-test-01")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "FAILED")

    # 5. workflow_run_id 조회
    def test_05_get_by_workflow_run_id(self):
        ev = _base_event("wf_obs_05", "USER_CONFIRMED")
        record_user_present_status(ev, agent_id="la-test-01")
        record = get_user_present_status("wf_obs_05")
        self.assertIsNotNone(record)
        self.assertEqual(record["workflow_run_id"], "wf_obs_05")
        self.assertEqual(record["status"], "USER_CONFIRMED")
        self.assertEqual(record["agent_id"], "la-test-01")

    # 6. agent_id별 목록 조회
    def test_06_list_by_agent_id(self):
        for i in range(3):
            ev = _base_event(f"wf_obs_06_{i}", "USER_CONFIRMED")
            record_user_present_status(ev, agent_id="la-agent-A")
        ev2 = _base_event("wf_obs_06_other", "CANCELLED")
        record_user_present_status(ev2, agent_id="la-agent-B")

        records_a = list_user_present_statuses(agent_id="la-agent-A")
        records_b = list_user_present_statuses(agent_id="la-agent-B")
        self.assertEqual(len(records_a), 3)
        self.assertEqual(len(records_b), 1)

    # 7. safe_to_execute=true reject
    def test_07_reject_safe_to_execute_true(self):
        ev = _base_event("wf_obs_07")
        ev["safe_to_execute"] = True
        result = record_user_present_status(ev)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "SAFE_TO_EXECUTE_MUST_BE_FALSE")
        self.assertIsNone(get_user_present_status("wf_obs_07"))

    # 8. token/cookie/session 포함 reject
    def test_08_reject_token_cookie_session(self):
        for field in ["token", "cookie", "session"]:
            clear_store_for_testing()
            ev = _base_event(f"wf_obs_08_{field}")
            ev[field] = "should-be-rejected"
            result = record_user_present_status(ev)
            self.assertFalse(result["ok"], f"{field} should be rejected")
            self.assertIn("FORBIDDEN_FIELD", result["error"])

    # 9. password/otp/certificate_password 포함 reject
    def test_09_reject_password_otp_cert(self):
        for field in ["password", "otp", "certificate_password"]:
            clear_store_for_testing()
            ev = _base_event(f"wf_obs_09_{field}")
            ev[field] = "secret"
            result = record_user_present_status(ev)
            self.assertFalse(result["ok"], f"{field} should be rejected")

    # 10. raw target_url 저장 금지
    def test_10_raw_target_url_not_stored(self):
        ev = _base_event("wf_obs_10")
        ev["target_url"] = "https://www.bank.co.kr/login"
        result = record_user_present_status(ev)
        self.assertFalse(result["ok"])
        record = get_user_present_status("wf_obs_10")
        self.assertIsNone(record)

    # 11. 조회 결과에 민감정보 없음
    def test_11_no_sensitive_in_record(self):
        ev = _base_event("wf_obs_11", "USER_CONFIRMED")
        record_user_present_status(ev, agent_id="la-test-01")
        record = get_user_present_status("wf_obs_11")
        forbidden = [
            "password",
            "otp",
            "certificate_password",
            "token",
            "cookie",
            "session",
            "device_token",
            "target_url",
        ]
        for field in forbidden:
            self.assertNotIn(field, record, f"{field} must not be in record")

    # 12. ack에 received_at 포함 (handler 반환값)
    def test_12_handler_returns_received_at(self):
        ev = _base_event("wf_obs_12", "USER_CONFIRMED")
        result = handle_user_present_status_event(ev, agent_id="la-test-01")
        self.assertTrue(result["ok"])
        self.assertIn("received_at", result)
        self.assertTrue(result["received_at"])
        self.assertFalse(result["safe_to_execute"])

    # 13. 기존 handler와 호환 — handler_get_status
    def test_13_handler_registry_compatibility(self):
        ev = _base_event("wf_obs_13", "CANCELLED")
        handle_user_present_status_event(ev, agent_id="la-test-01")
        record = handler_get_status("wf_obs_13")
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "CANCELLED")

    # 14. sender event 구조와 호환 (message_type 필드 포함)
    def test_14_sender_event_structure_compat(self):
        ev = {
            "message_type": "USER_PRESENT_STATUS",
            "workflow_run_id": "wf_obs_14",
            "status": "USER_CONFIRMED",
            "tenant_id": "haehan",
            "user_id": "u1",
            "site_id": "g2b",
            "safe_to_execute": False,
            "status_reason": "",
            "created_at": "2026-05-07T12:00:00+00:00",
        }
        result = record_user_present_status(ev, agent_id="la-test")
        self.assertTrue(result["ok"])

    # 15. DB write 없음 — sqlite/psycopg2/sqlalchemy 임포트 없음
    def test_15_no_db_write(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_store as m

        src = inspect.getsource(m)
        for mod in ["sqlite3", "psycopg2", "sqlalchemy", "pymongo", "motor"]:
            self.assertNotIn(f"import {mod}", src, f"{mod} import found in store")

    # 16. browser_worker/task_executor 호출 없음 (docstring 제외 실제 코드 검사)
    def test_16_no_browser_worker_task_executor(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_store as m

        src = inspect.getsource(m)
        # docstring/comment 제외 실제 import/call 라인만 검사
        code_lines = [
            ln
            for ln in src.splitlines()
            if not ln.strip().startswith("#") and not ln.strip().startswith('"""') and not ln.strip().startswith("'")
        ]
        code = "\n".join(code_lines)
        self.assertNotIn("import browser_worker", code)
        self.assertNotIn("ai_orchestrator.browser_tool.worker", code)
        self.assertNotIn("import task_executor", code)
        self.assertNotIn("browser_worker.", code)
        self.assertNotIn("task_executor.", code)

    # 17. click/type/fill/submit 없음
    def test_17_no_automation_calls(self):
        import inspect

        import ai_orchestrator.agent_hub.user_present_status_store as m

        src = inspect.getsource(m)
        for call in ["page.click", "page.type", "page.fill", "page.goto", ".submit("]:
            self.assertNotIn(call, src)

    # 18. 존재하지 않는 workflow_run_id는 None 반환
    def test_18_missing_workflow_run_id_returns_none(self):
        result = get_user_present_status("wf_nonexistent_9999")
        self.assertIsNone(result)

    # 19. validate_stored_user_present_status 정상 레코드 통과
    def test_19_validate_valid_record(self):
        record = {
            "workflow_run_id": "wf_valid",
            "status": "USER_CONFIRMED",
            "received_at": "2026-05-07T12:00:00+00:00",
            "safe_to_execute": False,
        }
        errors = validate_stored_user_present_status(record)
        self.assertEqual(errors, [])

    # 20. validate_stored_user_present_status 금지 필드 탐지
    def test_20_validate_rejects_forbidden_fields(self):
        record = {
            "workflow_run_id": "wf_bad",
            "status": "USER_CONFIRMED",
            "received_at": "2026-05-07T12:00:00+00:00",
            "safe_to_execute": False,
            "password": "secret",
        }
        errors = validate_stored_user_present_status(record)
        self.assertTrue(any("password" in e for e in errors))

    # 21. list_user_present_statuses 전체 반환 (agent_id 없음)
    def test_21_list_all_statuses(self):
        for i in range(4):
            record_user_present_status(
                _base_event(f"wf_obs_21_{i}", "USER_CONFIRMED"),
                agent_id=f"la-{i}",
            )
        all_records = list_user_present_statuses()
        self.assertGreaterEqual(len(all_records), 4)

    # 22. handler가 store에도 기록하는지 확인
    def test_22_handler_writes_to_store(self):
        ev = _base_event("wf_obs_22", "USER_CONFIRMED")
        handle_user_present_status_event(ev, agent_id="la-store-test")
        record = get_user_present_status("wf_obs_22")
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "USER_CONFIRMED")
        self.assertEqual(record["agent_id"], "la-store-test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
