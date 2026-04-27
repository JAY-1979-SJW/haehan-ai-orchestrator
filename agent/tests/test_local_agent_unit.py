"""local_agent — HTTP 기반 루프 통합 테스트 (B안 4단계).

approval_policy / result_spool 편입 이후 버전. api_client /
task_executor 는 stub, 파일 경로 정책은 tmp_path 로 격리한다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


# ──────────────────────────────────────────────────────────────────
# fixture: 격리된 work / output / spool 디렉터리
# ──────────────────────────────────────────────────────────────────
@pytest.fixture()
def env(tmp_path, monkeypatch):
    from agent import config as _cfg
    work = tmp_path / "work"
    out = tmp_path / "output"
    spool = tmp_path / "spool"
    work.mkdir(); out.mkdir()
    sample = work / "sample.xlsx"
    sample.write_bytes(b"dummy xlsx")
    monkeypatch.setattr(_cfg, "AGENT_WORK_DIR", work)
    monkeypatch.setattr(_cfg, "AGENT_OUTPUT_DIR", out)
    # API 필요 env 는 삭제 — 테스트에서 명시 전달.
    monkeypatch.delenv("AGENT_API_URL", raising=False)
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    monkeypatch.delenv("AGENT_SPOOL_DIR", raising=False)
    return {
        "tmp": tmp_path, "work": work, "out": out, "spool": spool,
        "sample": sample,
        "save_as": out / "out.xlsx",
    }


def _low_task(env, tid="t-low"):
    return {
        "id": tid, "action": "excel.run_poc",
        "file_path": str(env["sample"]),
        "save_as": str(env["out"] / f"{tid}.xlsx"),
    }


def _medium_task(env, tid="t-med", token=None):
    t = {
        "id": tid, "action": "excel.write_cell",
        "file_path": str(env["sample"]),
        "save_as": str(env["out"] / f"{tid}.xlsx"),
        "cell_ref": "B2", "value": "X",
    }
    if token:
        t["approval_token"] = token
        t["approved_by"] = "tester"
    return t


# ──────────────────────────────────────────────────────────────────
# fetch / report 위임
# ──────────────────────────────────────────────────────────────────
def test_fetch_task_delegates_to_api_client(monkeypatch):
    from agent import local_agent as la
    from agent import api_client

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: ({"id": "t-1", "action": "excel.run_poc"}, None),
    )
    task, err = la.fetch_task("http://x", "tok")
    assert err is None
    assert task["id"] == "t-1"


def test_report_result_delegates_to_api_client(monkeypatch):
    from agent import local_agent as la
    from agent import api_client
    seen = {}
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (seen.setdefault("r", r), None)[1],
    )
    err = la.report_result("http://x", "tok", {"id": "t"})
    assert err is None
    assert seen["r"]["id"] == "t"


# ──────────────────────────────────────────────────────────────────
# run_agent_loop — low action 자동 승인
# ──────────────────────────────────────────────────────────────────
def test_low_action_passes_gate_and_reports(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_low_task(env, "t-low-1")]
    reports: list[dict] = []

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: {"ok": True, "data": {"done": True}, "error": None},
    )

    n = la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=3, spool_dir=env["spool"],
    )
    assert n == 1
    r = reports[0]
    assert r["id"] == "t-low-1"
    assert r["action"] == "excel.run_poc"
    assert r["category"] == "excel_com"
    assert r["risk_level"] == "low"
    assert r["approved"] is True
    assert r["ok"] is True
    assert r["error"] is None
    assert isinstance(r["duration_ms"], int)
    assert r["started_at"] and r["finished_at"]
    assert r["idempotency_key"]
    # spool 없어야 함
    assert not any(env["spool"].glob("*.json")) if env["spool"].exists() else True


# ──────────────────────────────────────────────────────────────────
# medium action — 승인 게이트
# ──────────────────────────────────────────────────────────────────
def test_medium_action_without_token_blocked_and_reported(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_medium_task(env, "t-med-1")]
    reports: list[dict] = []
    exec_called = {"n": 0}

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )

    def _exec(t):
        exec_called["n"] += 1
        return {"ok": True, "data": {}, "error": None}

    monkeypatch.setattr(task_executor, "execute_task", _exec)

    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=3, spool_dir=env["spool"],
    )
    # 실행은 일어나지 않고 게이트에서 차단
    assert exec_called["n"] == 0
    r = reports[0]
    assert r["ok"] is False
    assert r["error"] == "approval_required"
    assert r["approved"] is False
    assert r["risk_level"] == "medium"
    assert r["category"] == "excel_com"


def test_medium_action_with_token_passes_gate(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_medium_task(env, "t-med-ok", token="tok-123")]
    reports: list[dict] = []

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: {"ok": True, "data": {"wrote": True}, "error": None},
    )

    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=2, spool_dir=env["spool"],
    )
    r = reports[0]
    assert r["ok"] is True
    assert r["approved"] is True
    assert r["approved_by"] == "tester"
    assert r["error"] is None


# ──────────────────────────────────────────────────────────────────
# 경로 정책 — save_as 디렉터리 밖
# ──────────────────────────────────────────────────────────────────
def test_save_as_outside_output_dir_blocked_at_gate(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    bad_task = {
        "id": "t-bad", "action": "excel.run_poc",
        "file_path": str(env["sample"]),
        "save_as": str(env["tmp"] / "outside.xlsx"),  # AGENT_OUTPUT_DIR 밖
    }
    tasks = [bad_task]
    reports: list[dict] = []

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: pytest.fail("executor must not be called for blocked task"),
    )

    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=2, spool_dir=env["spool"],
    )
    assert reports[0]["ok"] is False
    assert reports[0]["error"] == "output_path_not_allowed"


# ──────────────────────────────────────────────────────────────────
# 감사 로그 필드 — 필수 키 존재
# ──────────────────────────────────────────────────────────────────
_AUDIT_KEYS = {
    "id", "action", "category", "risk_level",
    "approved", "approved_by",
    "ok", "error",
    "started_at", "finished_at", "duration_ms",
    "idempotency_key",
}


def test_audit_fields_present_for_allowed_task(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor
    tasks = [_low_task(env, "t-audit")]
    reports: list[dict] = []
    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: {"ok": True, "data": {}, "error": None},
    )
    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=2, spool_dir=env["spool"],
    )
    assert _AUDIT_KEYS.issubset(reports[0].keys())


def test_audit_fields_present_for_blocked_task(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor
    tasks = [_medium_task(env, "t-blk")]
    reports: list[dict] = []
    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )
    monkeypatch.setattr(task_executor, "execute_task", lambda t: None)
    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=2, spool_dir=env["spool"],
    )
    assert _AUDIT_KEYS.issubset(reports[0].keys())
    assert reports[0]["ok"] is False


def test_sensitive_keys_scrubbed_from_result_data(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_low_task(env, "t-sanit")]
    reports: list[dict] = []
    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )
    # executor 가 실수로 토큰을 data 에 넣었다고 가정
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: {"ok": True, "data": {
            "value": "ok", "approval_token": "LEAKY", "session": "X",
        }, "error": None},
    )
    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=2, spool_dir=env["spool"],
    )
    r = reports[0]
    assert "approval_token" not in r["data"]
    assert "session" not in r["data"]
    assert r["data"]["value"] == "ok"


# ──────────────────────────────────────────────────────────────────
# result_spool 통합 — report 실패 → spool → 다음 루프 flush
# ──────────────────────────────────────────────────────────────────
def test_report_failure_enqueues_to_spool(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_low_task(env, "t-spool-1")]
    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda *a, **k: api_client.API_UNREACHABLE,
    )
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: {"ok": True, "data": {}, "error": None},
    )

    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=1, spool_dir=env["spool"],
    )
    spooled = list(env["spool"].glob("*.result.json"))
    assert len(spooled) == 1
    body = json.loads(spooled[0].read_text(encoding="utf-8"))
    assert body["id"] == "t-spool-1"
    assert "idempotency_key" in body


def test_next_loop_flushes_spooled_results(monkeypatch, env):
    """첫 loop: report 실패 → spool. 두 번째 loop: report 성공 → flush."""
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_low_task(env, "t-flush-1")]
    report_calls = {"n": 0}

    def _flaky_report(api, tok, r):
        report_calls["n"] += 1
        if report_calls["n"] == 1:
            return api_client.API_UNREACHABLE  # 첫 시도 실패
        return None  # flush 단계는 성공

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(api_client, "report_result", _flaky_report)
    monkeypatch.setattr(
        task_executor, "execute_task",
        lambda t: {"ok": True, "data": {}, "error": None},
    )

    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=3, spool_dir=env["spool"],
    )
    # 2번째 report (== spool flush) 가 성공하면 파일이 지워진다
    assert list(env["spool"].glob("*.result.json")) == []
    assert report_calls["n"] >= 2


def test_spool_dedupes_on_idempotency_key(monkeypatch, env):
    """같은 결과가 반복 enqueue 되어도 파일은 1개만."""
    from agent import local_agent as la
    from agent import api_client, task_executor

    calls = {"fetch": 0}

    def _fetch(api, tok):
        calls["fetch"] += 1
        if calls["fetch"] > 3:
            return None, None
        # 매 iteration 같은 id + action. started_at 이 다르면 key 가 달라지므로
        # 이 테스트에서는 idempotency_key 를 외부 강제 주입해 dedup 확인.
        return None, None  # fetch 는 비워두고 수동 enqueue 로 검증

    monkeypatch.setattr(api_client, "fetch_task", _fetch)
    monkeypatch.setattr(
        api_client, "report_result",
        lambda *a, **k: api_client.API_UNREACHABLE,
    )

    from agent import result_spool as rs
    # 같은 key 로 3번 enqueue
    rs.enqueue_failed_result(env["spool"], {"idempotency_key": "SAME", "id": "t"})
    rs.enqueue_failed_result(env["spool"], {"idempotency_key": "SAME", "id": "t"})
    rs.enqueue_failed_result(env["spool"], {"idempotency_key": "SAME", "id": "t"})
    assert len(list(env["spool"].glob("*.result.json"))) == 1


# ──────────────────────────────────────────────────────────────────
# 운영 요건 — loop 생존 / api 에러 / stop_file
# ──────────────────────────────────────────────────────────────────
def test_loop_survives_handler_crash(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client, task_executor

    tasks = [_low_task(env, "t-crash")]
    reports: list[dict] = []

    monkeypatch.setattr(
        api_client, "fetch_task",
        lambda api, tok: (tasks.pop(0) if tasks else None, None),
    )
    monkeypatch.setattr(
        api_client, "report_result",
        lambda api, tok, r: (reports.append(r), None)[1],
    )

    def _boom(t):
        raise RuntimeError("simulated")

    monkeypatch.setattr(task_executor, "execute_task", _boom)

    la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=2, spool_dir=env["spool"],
    )
    assert reports[0]["ok"] is False
    assert reports[0]["error"].startswith("execute_crashed:")


def test_loop_requires_api_url(env):
    from agent import local_agent as la
    with pytest.raises(ValueError):
        la.run_agent_loop("", "tok", max_iterations=1, spool_dir=env["spool"])


def test_loop_honors_stop_file(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client
    monkeypatch.setattr(api_client, "fetch_task", lambda *a, **k: (None, None))
    monkeypatch.setattr(api_client, "report_result", lambda *a, **k: None)
    stop = env["tmp"] / "stop"
    stop.write_text("")
    n = la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=99,
        stop_file=stop, spool_dir=env["spool"],
    )
    assert n == 0


def test_fetch_error_does_not_crash_loop(monkeypatch, env):
    from agent import local_agent as la
    from agent import api_client
    calls = {"n": 0}

    def _flaky(api, tok):
        calls["n"] += 1
        if calls["n"] == 1:
            return None, api_client.API_UNREACHABLE
        return None, None

    monkeypatch.setattr(api_client, "fetch_task", _flaky)
    monkeypatch.setattr(api_client, "report_result", lambda *a, **k: None)
    # 단지 loop 가 crash 없이 돌아야 함
    n = la.run_agent_loop(
        "http://x", "tok",
        poll_seconds=0.01, max_iterations=3, spool_dir=env["spool"],
    )
    assert n == 0
    assert calls["n"] >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
