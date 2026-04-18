import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_orchestrator import audit_logger
from pathlib import Path


def _clear_log():
    p = audit_logger._LOG_PATH
    if p.exists():
        p.write_text("", encoding="utf-8")


def test_log_event_appends():
    _clear_log()
    audit_logger.log_event(
        event_type="TASK_RECEIVED", task_id="T-LOG-001",
        action_type="read_file", target="/tmp/x.txt", actor="test"
    )
    audit_logger.log_event(
        event_type="RISK_ASSESSED", task_id="T-LOG-001",
        risk_level="low", actor="system"
    )
    logs = audit_logger.read_recent_logs(limit=20)
    assert len(logs) == 2
    assert logs[0]["event_type"] == "TASK_RECEIVED"
    assert logs[1]["event_type"] == "RISK_ASSESSED"
    print("PASS: log_event 2회 후 read_recent_logs=2건")


def test_read_recent_logs_limit():
    _clear_log()
    for i in range(5):
        audit_logger.log_event("DRY_RUN_RETURNED", f"T-LOG-{i:03d}", actor="test")
    logs = audit_logger.read_recent_logs(limit=2)
    assert len(logs) == 2
    assert logs[-1]["task_id"] == "T-LOG-004"
    print("PASS: read_recent_logs(limit=2) 마지막 2건 반환")


def test_log_file_created_automatically():
    p = audit_logger._LOG_PATH
    if p.exists():
        p.unlink()
    audit_logger.log_event("TASK_RECEIVED", "T-LOG-AUTO", actor="test")
    assert p.exists()
    print("PASS: 파일 없어도 자동 생성")


if __name__ == "__main__":
    test_log_event_appends()
    test_read_recent_logs_limit()
    test_log_file_created_automatically()
    print("\n모든 audit_logger 테스트 통과")
