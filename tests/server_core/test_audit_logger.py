import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_orchestrator.audit import audit_logger


def _clear_log():
    p = audit_logger._LOG_PATH
    if p.exists():
        p.write_text("", encoding="utf-8")


def test_log_event_appends():
    _clear_log()
    audit_logger.log_event(
        event_type="TASK_RECEIVED",
        task_id="T-LOG-001",
        action_type="read_file",
        target="/tmp/x.txt",  # noqa: S108
        actor="test",
    )
    audit_logger.log_event(event_type="RISK_ASSESSED", task_id="T-LOG-001", risk_level="low", actor="system")
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


def test_log_event_masks_sensitive_note():
    _clear_log()
    audit_logger.log_event(
        event_type="TASK_RECEIVED",
        task_id="T-LOG-MASK",
        actor="test",
        note="token=Bearer abcdefghijklmnop123456",
    )
    logs = audit_logger.read_recent_logs(limit=1)
    assert "abcdefghijklmnop123456" not in logs[0]["note"]
    assert "Bearer" in logs[0]["note"]
    print("PASS: note의 Bearer 토큰 값이 마스킹됨")


def test_log_event_keeps_token_id_identifier_unmasked():
    _clear_log()
    audit_logger.log_event(
        event_type="TASK_RECEIVED",
        task_id="T-LOG-MASK2",
        actor="test",
        token_id="tok_abc123",  # noqa: S106 - 실제 비밀 아님, 식별자 보존 확인용 시험 값
    )
    logs = audit_logger.read_recent_logs(limit=1)
    assert logs[0]["token_id"] == "tok_abc123"  # noqa: S105 - 실제 비밀 아님, 식별자 보존 확인용 시험 값
    print("PASS: token_id는 비밀이 아닌 식별자라 그대로 유지됨")


def test_log_event_keeps_email_actor_unmasked():
    _clear_log()
    audit_logger.log_event(
        event_type="APPROVAL_GRANTED",
        task_id="T-LOG-ACTOR",
        actor="owner@haehan.ai",
        role="owner",
    )
    logs = audit_logger.read_recent_logs(limit=1)
    assert logs[0]["actor"] == "owner@haehan.ai"
    print("PASS: actor(이메일 식별자)는 그대로 유지됨 — '누가 했는지' 보존")


def test_log_event_keeps_normal_fields_unmasked():
    _clear_log()
    audit_logger.log_event(
        event_type="TASK_RECEIVED",
        task_id="T-LOG-PLAIN",
        actor="test",
        action_type="read_file",
        target="/tmp/x.txt",  # noqa: S108
    )
    logs = audit_logger.read_recent_logs(limit=1)
    assert logs[0]["task_id"] == "T-LOG-PLAIN"
    assert logs[0]["actor"] == "test"
    assert logs[0]["action_type"] == "read_file"
    assert logs[0]["target"] == "/tmp/x.txt"  # noqa: S108
    print("PASS: 민감 키가 아닌 일반 필드는 그대로 유지됨")


if __name__ == "__main__":
    test_log_event_appends()
    test_read_recent_logs_limit()
    test_log_file_created_automatically()
    test_log_event_masks_sensitive_note()
    test_log_event_keeps_token_id_identifier_unmasked()
    test_log_event_keeps_email_actor_unmasked()
    test_log_event_keeps_normal_fields_unmasked()
    print("\n모든 audit_logger 테스트 통과")
