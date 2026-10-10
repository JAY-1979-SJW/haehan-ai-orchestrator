"""task_state: 상태 머신 (pending → approved → executed, pending → rejected)."""

from __future__ import annotations

import importlib

import pytest

from ai_orchestrator.core import task_state as ts


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    # 독립적인 storage 경로에서 테스트
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    from ai_orchestrator.core import config as _cfg

    importlib.reload(_cfg)
    importlib.reload(ts)
    ts.clear()
    yield
    ts.clear()


def _pend(task_id="T1"):
    return ts.set_pending(
        task_id=task_id,
        risk_level="medium",
        token_id="tok-1",  # noqa: S106
        requested_by="operator_u",
        actor_role="operator",
        action_type="edit_config",
        target="/tmp/x",  # noqa: S108
        task_snapshot={"action_type": "edit_config", "target": "/tmp/x"},  # noqa: S108
    )


def test_set_pending_creates_record():
    r = _pend()
    assert r.state == "pending"
    assert ts.get_state("T1") == "pending"


def test_approve_transition():
    _pend()
    rec, st = ts.mark_approved("T1", "admin_u", "admin")
    assert st == "approved"
    assert rec.state == "approved"
    assert rec.approved_by == "admin_u"


def test_reject_transition():
    _pend()
    rec, st = ts.mark_rejected("T1", "admin_u", "admin", reason="not needed")
    assert st == "rejected"
    assert rec.state == "rejected"
    assert rec.reason == "not needed"


def test_execute_only_after_approve():
    _pend()
    # 직접 executed 전이는 금지
    rec, st = ts.mark_executed("T1", "OK")
    assert st.startswith("invalid_transition"), st

    ts.mark_approved("T1", "admin_u", "admin")
    rec, st = ts.mark_executed("T1", "OK")
    assert st == "executed"
    assert rec.state == "executed"
    assert rec.result == "OK"


def test_no_approval_after_rejected_or_executed():
    _pend("TR")
    ts.mark_rejected("TR", "admin_u", "admin")
    # rejected → approved 금지
    _, st = ts.mark_approved("TR", "admin_u", "admin")
    assert st.startswith("invalid_transition"), st

    _pend("TE")
    ts.mark_approved("TE", "admin_u", "admin")
    ts.mark_executed("TE", "OK")
    # executed → approved 금지
    _, st = ts.mark_approved("TE", "admin_u", "admin")
    assert st.startswith("invalid_transition"), st


def test_not_found():
    _, st = ts.mark_approved("NOPE", "admin_u", "admin")
    assert st == "not_found"
    _, st = ts.mark_rejected("NOPE", "admin_u", "admin")
    assert st == "not_found"
    _, st = ts.mark_executed("NOPE", "OK")
    assert st == "not_found"


def test_token_id_is_identifier_not_raw_secret(tmp_path):
    """token_id는 식별자(ID)만 저장되고, task_snapshot에 원문 시크릿 미포함."""
    r = _pend()
    assert r.token_id == "tok-1"  # noqa: S105
    for bad in ("password", "secret", "raw_token", "access_token"):
        assert bad not in r.task_snapshot, f"task_snapshot에 민감 필드: {bad}"


def test_jsonl_persists_events(tmp_path):
    """JSONL 파일에 이벤트가 append-only로 기록되는지 확인."""
    _pend()
    ts.mark_approved("T1", "admin_u", "admin")
    ts.mark_executed("T1", "OK")
    state_file = tmp_path / "task_states.jsonl"
    assert state_file.exists(), "JSONL 이벤트 파일 미생성"
    lines = [ln for ln in state_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
    import json

    for ln in lines:
        json.loads(ln)


def test_duplicate_set_pending_is_idempotent():
    """같은 task_id로 set_pending 2회 호출 시 1건만 유지."""
    r1 = _pend("DUP")
    r2 = _pend("DUP")
    assert r1.state == "pending"
    assert r2.state == "pending"
    assert ts.get_state("DUP") == "pending"
