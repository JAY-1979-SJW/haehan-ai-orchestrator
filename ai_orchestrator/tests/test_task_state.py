"""task_state: 상태 머신 (pending → approved → executed, pending → rejected)."""
from __future__ import annotations

import importlib
import os

import pytest

from ai_orchestrator import task_state as ts


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    # 독립적인 storage 경로에서 테스트
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    from ai_orchestrator import config as _cfg
    importlib.reload(_cfg)
    importlib.reload(ts)
    ts.clear()
    yield
    ts.clear()


def _pend(task_id="T1"):
    return ts.set_pending(
        task_id=task_id, risk_level="medium", token_id="tok-1",
        requested_by="operator_u", actor_role="operator",
        action_type="edit_config", target="/tmp/x",
        task_snapshot={"action_type": "edit_config", "target": "/tmp/x"},
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
