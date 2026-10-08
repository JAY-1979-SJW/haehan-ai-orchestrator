"""bulk_send.main 의 result 초기화 — 가짜 sender 만 사용, 실제 발송·사이트 접속 없음."""

from __future__ import annotations

import ast
import inspect
import sys

import pytest

from scripts.hanafax import bulk_send as bs


@pytest.fixture
def harness(monkeypatch):
    saved: list[tuple[int, object]] = []
    monkeypatch.setattr(bs, "_get_creds", lambda: ("u", "p"))
    monkeypatch.setattr(bs, "load_batch", lambda n: {"fax_numbers": ["1", "2"]})
    monkeypatch.setattr(bs, "save_result", lambda n, r: saved.append((n, r)))
    monkeypatch.setattr(bs.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["bulk_send", "--batch", "1"])
    return saved


def test_normal_path_unchanged(monkeypatch, harness):
    monkeypatch.setattr(bs, "send_bulk_batch", lambda **kw: {"ok": True, "job_id": "J"})
    bs.main()
    assert harness == [(1, {"ok": True, "job_id": "J"})]


def test_retry_then_success(monkeypatch, harness):
    seq = [{"ok": False, "retry": True}, {"ok": True, "job_id": "J2"}]
    monkeypatch.setattr(bs, "send_bulk_batch", lambda **kw: seq.pop(0))
    bs.main()
    assert harness[0][1] == {"ok": True, "job_id": "J2"} and not seq


def test_unattempted_send_loop_is_explicit_failure(monkeypatch, harness):
    """발송 루프가 한 번도 돌지 않는 가상 분기: UnboundLocal/None 이 아니라 실패 결과로 처리."""
    calls: list[object] = []
    monkeypatch.setattr(bs, "send_bulk_batch", lambda **kw: calls.append(kw) or {"ok": True})
    monkeypatch.setattr(bs, "range", lambda *a: iter(()), raising=False)
    bs.main()
    assert calls == []
    assert harness[0][1]["ok"] is False and harness[0][1]["error"] == "not_attempted"


def test_result_initialised_to_failure_value():
    tree = ast.parse(inspect.getsource(bs.main).lstrip())
    inits = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        and "result" in ast.unparse(n.targets[0] if isinstance(n, ast.Assign) else n.target)
        and isinstance(n.value, ast.Dict)
    ]
    assert inits, "result 가 dict 실패값으로 초기화되지 않음"
    assert "'ok': False" in ast.unparse(inits[0].value)
