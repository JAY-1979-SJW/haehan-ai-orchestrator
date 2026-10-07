"""EUM 최종 제출(submit=True) 결과 확인 시험 — 가짜 객체만 사용, 사이트 접속 없음."""

from __future__ import annotations

import contextlib

import pytest

from scripts.eum import router

WF = {"key": "device_registration"}


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    import scripts.eum.run_log as run_log
    import scripts.eum.work_plan as work_plan
    import scripts.common.gate as gate

    monkeypatch.setattr(work_plan, "build_action_plan", lambda *a, **k: {"valid": True})
    monkeypatch.setattr(work_plan, "save_action_plan", lambda plan: "plan.json")
    monkeypatch.setattr(work_plan, "print_action_plan", lambda *a, **k: None)
    monkeypatch.setattr(run_log, "work_run", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(gate, "force_approved", lambda: contextlib.nullcontext())


def _patch(monkeypatch, name, fn):
    monkeypatch.setattr(router, name, fn)


@pytest.mark.parametrize(
    "key,fn", [("device_registration", "_cmd_registration"), ("device_deregistration", "_cmd_deregistration")]
)
def test_submit_failure_raises(monkeypatch, key, fn):
    _patch(monkeypatch, fn, lambda *a, **k: {"success": False, "error": "boom"})
    with pytest.raises(RuntimeError, match="boom"):
        router._execute_approval_workflow({"key": key}, ["A", "B"])


@pytest.mark.parametrize(
    "key,fn", [("device_registration", "_cmd_registration"), ("device_deregistration", "_cmd_deregistration")]
)
def test_submit_success_unchanged(monkeypatch, key, fn):
    calls = []
    _patch(monkeypatch, fn, lambda *a, **k: calls.append(k) or {"success": True})
    assert router._execute_approval_workflow({"key": key}, ["A", "B"]) is None
    assert calls == [{"submit": True}]


def test_submit_exception_propagates(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("net")

    _patch(monkeypatch, "_cmd_registration", _raise)
    with pytest.raises(ValueError):
        router._execute_approval_workflow(WF, ["A"])


def test_submit_non_dict_result_is_not_error(monkeypatch):
    # prepare 경로와 동일: dict 가 아닌 반환(사용법 출력 등)은 검사 대상 아님
    _patch(monkeypatch, "_cmd_registration", lambda *a, **k: None)
    router._execute_approval_workflow(WF, ["A"])


def test_prepare_path_unchanged(monkeypatch):
    _patch(monkeypatch, "_cmd_registration", lambda *a, **k: {"success": False, "error": "pe"})
    with pytest.raises(RuntimeError, match="pe"):
        router._prepare_approval_workflow(WF, ["A"])
    _patch(monkeypatch, "_cmd_registration", lambda *a, **k: {"success": True})
    router._prepare_approval_workflow(WF, ["A"])
