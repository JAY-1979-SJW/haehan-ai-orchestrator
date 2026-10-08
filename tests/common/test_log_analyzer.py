"""
log_analyzer 단위 테스트 (5단계)
- 빈 로그 안전 처리
- blocked/preview/executed 카운트 정상 집계
- pending approvals 정상 집계
- ai summary mock 정상 반환
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.monitoring.log_analyzer as log_analyzer

# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_jsonl(path: str, records: list) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _history_entry(task_id: str, action_type: str, status: str, risk_level: str = "low", note: str = "") -> dict:
    return {
        "timestamp": "2026-04-18T12:00:00",
        "task_id": task_id,
        "action_type": action_type,
        "target": f"/tmp/{task_id}",
        "execution_status": status,
        "risk_level": risk_level,
        "exit_code": 0,
        "preview_only": status == "PREVIEW_ONLY",
        "actor": "tester",
        "note": note,
    }


def _audit_entry(task_id: str, event_type: str, risk_level: str = None, note: str = "") -> dict:  # noqa: RUF013
    return {
        "timestamp": "2026-04-18T12:00:00",
        "event_type": event_type,
        "task_id": task_id,
        "action_type": "read_file",
        "actor": "tester",
        "risk_level": risk_level,
        "note": note,
    }


# ── Tests: 빈 로그 안전 처리 ────────────────────────────────────────────────


def test_empty_logs_safe_summarize(tmp_path, monkeypatch):
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))

    result = log_analyzer.summarize_recent_activity()

    assert result["total_tasks"] == 0
    assert result["blocked_count"] == 0
    assert result["executed_count"] == 0
    assert result["preview_count"] == 0
    assert result["failed_count"] == 0
    assert result["top_action_types"] == []
    assert result["top_blocked_reasons"] == []
    assert result["recent_tasks"] == []


def test_empty_logs_safe_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))

    result = log_analyzer.summarize_failures()
    assert result["total_failures"] == 0
    assert result["recent_errors"] == []


def test_empty_logs_safe_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))

    result = log_analyzer.summarize_pending_approvals()
    assert result["pending_count"] == 0
    assert result["pending_approvals"] == []


def test_nonexistent_file_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "no_such.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "no_such2.jsonl"))

    result = log_analyzer.summarize_recent_activity()
    assert result["total_tasks"] == 0


# ── Tests: 카운트 집계 ───────────────────────────────────────────────────────


def test_executed_count(tmp_path, monkeypatch):
    history_path = str(tmp_path / "history.jsonl")
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(
        history_path,
        [
            _history_entry("t1", "read_file", "EXECUTED"),
            _history_entry("t2", "list_dir", "EXECUTED"),
            _history_entry("t3", "edit_config", "PREVIEW_ONLY", risk_level="medium"),
        ],
    )
    _write_jsonl(audit_path, [])

    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", history_path)
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)

    result = log_analyzer.summarize_recent_activity()
    assert result["total_tasks"] == 3
    assert result["executed_count"] == 2
    assert result["preview_count"] == 1
    assert result["blocked_count"] == 0


def test_blocked_count(tmp_path, monkeypatch):
    history_path = str(tmp_path / "history.jsonl")
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(
        history_path,
        [
            _history_entry(
                "t1", "restart_service", "BLOCKED", risk_level="high", note="risk level 'high' is always blocked"
            ),
            _history_entry(
                "t2", "delete_file", "BLOCKED", risk_level="critical", note="critical actions are always blocked"
            ),
            _history_entry("t3", "read_file", "EXECUTED"),
        ],
    )
    _write_jsonl(audit_path, [])

    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", history_path)
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)

    result = log_analyzer.summarize_recent_activity()
    assert result["blocked_count"] == 2
    assert result["executed_count"] == 1
    assert len(result["top_blocked_reasons"]) >= 1


def test_failed_count_from_audit(tmp_path, monkeypatch):
    history_path = str(tmp_path / "history.jsonl")
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(history_path, [])
    _write_jsonl(
        audit_path,
        [
            _audit_entry("t1", "EXECUTION_FAILED", note="unexpected error"),
            _audit_entry("t2", "EXECUTION_FAILED", note="adapter timeout"),
            _audit_entry("t3", "TASK_RECEIVED"),
        ],
    )

    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", history_path)
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)

    result = log_analyzer.summarize_recent_activity()
    assert result["failed_count"] == 2


def test_top_action_types(tmp_path, monkeypatch):
    history_path = str(tmp_path / "history.jsonl")
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(
        history_path,
        [
            _history_entry("t1", "read_file", "EXECUTED"),
            _history_entry("t2", "read_file", "EXECUTED"),
            _history_entry("t3", "list_dir", "EXECUTED"),
        ],
    )
    _write_jsonl(audit_path, [])

    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", history_path)
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)

    result = log_analyzer.summarize_recent_activity()
    top = dict(result["top_action_types"])
    assert top.get("read_file") == 2
    assert top.get("list_dir") == 1


# ── Tests: Pending Approvals ─────────────────────────────────────────────────


def test_pending_approvals_basic(tmp_path, monkeypatch):
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(
        audit_path,
        [
            _audit_entry("task-A", "APPROVAL_ISSUED", risk_level="medium"),
            _audit_entry("task-B", "APPROVAL_ISSUED", risk_level="high"),
            _audit_entry("task-A", "APPROVAL_GRANTED"),  # task-A is no longer pending
        ],
    )

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "no.jsonl"))

    result = log_analyzer.summarize_pending_approvals()
    assert result["pending_count"] == 1
    pending_ids = [p["task_id"] for p in result["pending_approvals"]]
    assert "task-B" in pending_ids
    assert "task-A" not in pending_ids


def test_pending_approvals_rejected_excluded(tmp_path, monkeypatch):
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(
        audit_path,
        [
            _audit_entry("task-X", "APPROVAL_ISSUED", risk_level="high"),
            _audit_entry("task-X", "APPROVAL_REJECTED"),
        ],
    )

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "no.jsonl"))

    result = log_analyzer.summarize_pending_approvals()
    assert result["pending_count"] == 0


def test_pending_approvals_all_cleared(tmp_path, monkeypatch):
    audit_path = str(tmp_path / "audit.jsonl")
    _write_jsonl(
        audit_path,
        [
            _audit_entry("t1", "APPROVAL_ISSUED"),
            _audit_entry("t2", "APPROVAL_ISSUED"),
            _audit_entry("t1", "APPROVAL_GRANTED"),
            _audit_entry("t2", "APPROVAL_REJECTED"),
        ],
    )

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", audit_path)
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "no.jsonl"))

    result = log_analyzer.summarize_pending_approvals()
    assert result["pending_count"] == 0


# ── Tests: AI Summary Mock ───────────────────────────────────────────────────


def test_ai_summary_mock_no_data():
    summary = {
        "total_tasks": 0,
        "blocked_count": 0,
        "pending_approvals": 0,
        "executed_count": 0,
        "failed_count": 0,
        "preview_count": 0,
        "top_blocked_reasons": [],
    }
    result = log_analyzer.generate_ai_ops_summary(summary)
    assert isinstance(result, str)
    assert len(result) > 10


def test_ai_summary_mock_with_data():
    summary = {
        "total_tasks": 10,
        "blocked_count": 4,
        "pending_approvals": 2,
        "executed_count": 5,
        "failed_count": 1,
        "preview_count": 1,
        "top_blocked_reasons": [("risk level 'high' is always blocked", 3)],
    }
    result = log_analyzer.generate_ai_ops_summary(summary)
    assert isinstance(result, str)
    assert "10" in result or "작업" in result


def test_ai_summary_contains_pending_warning():
    summary = {
        "total_tasks": 5,
        "blocked_count": 1,
        "pending_approvals": 3,
        "executed_count": 3,
        "failed_count": 0,
        "preview_count": 1,
        "top_blocked_reasons": [],
    }
    result = log_analyzer.generate_ai_ops_summary(summary)
    assert "3" in result or "대기" in result or "pending" in result.lower()


# ── Tests: JSONL 파싱 실패 ────────────────────────────────────────────────────


def test_malformed_jsonl_skipped(tmp_path, monkeypatch):
    history_path = str(tmp_path / "history.jsonl")
    with Path(history_path).open("w", encoding="utf-8") as f:
        f.write('{"task_id":"good","execution_status":"EXECUTED","action_type":"read_file"}\n')
        f.write("NOT_VALID_JSON\n")
        f.write('{"task_id":"good2","execution_status":"BLOCKED","action_type":"delete_file"}\n')

    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", history_path)
    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "no.jsonl"))

    result = log_analyzer.summarize_recent_activity()
    assert result["total_tasks"] == 2  # malformed line skipped
    assert result["executed_count"] == 1
    assert result["blocked_count"] == 1
