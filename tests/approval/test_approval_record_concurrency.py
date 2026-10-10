"""approval_record_router 핸들러(def, 스레드풀 실행) 동시 쓰기 시 JSONL 무결성 시험.

tmp 경로 + monkeypatch 격리 — 운영 경로·네트워크 미사용.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import ai_orchestrator.browser_tool.approval.approval_record_router as router_mod
from ai_orchestrator.asgi import app

_N = 20


@pytest.fixture
def client(monkeypatch, tmp_path):
    import ai_orchestrator.core.config as config

    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    store = tmp_path / "approvals.jsonl"
    monkeypatch.setattr(router_mod, "APPROVAL_RECORD_STORE_PATH", store)
    return TestClient(app), store


def _create_body(i: int) -> dict:
    return {
        "workflow_run_id": f"wf_{i}",
        "workflow_id": "w",
        "action_name": "browser.execute_click",
        "operation_type": "click",
        "requested_by": "u",
        "requested_role": "admin",
    }


def test_concurrent_create_and_approve_keep_jsonl_intact(client):
    c, store = client
    with ThreadPoolExecutor(max_workers=8) as ex:
        created = list(ex.map(lambda i: c.post("/api/v1/browser-approvals/requests", json=_create_body(i)), range(_N)))
    assert all(r.status_code == 200 for r in created)
    ids = [r.json()["approval_id"] for r in created]
    assert len(set(ids)) == _N

    dec = {"decided_by": "a", "decided_role": "admin"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        approved = list(ex.map(lambda a: c.post(f"/api/v1/browser-approvals/requests/{a}/approve", json=dec), ids))
    assert all(r.status_code == 200 for r in approved)

    lines = [ln for ln in store.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2 * _N
    records = [json.loads(ln) for ln in lines]  # 각 줄이 유효 JSON
    assert sum(r["approval_status"] == "APPROVED" for r in records) == _N
    listed = c.get("/api/v1/browser-approvals/requests", params={"status": "APPROVED"}).json()
    assert listed["count"] == _N


def test_concurrent_duplicate_approve_only_one_wins(client):
    """상태 전이 검증: 같은 요청의 동시 approve 4건 중 정확히 1건만 200, 나머지 409, 기록은 요청+승인 2줄."""
    c, store = client
    aid = c.post("/api/v1/browser-approvals/requests", json=_create_body(0)).json()["approval_id"]
    dec = {"decided_by": "a", "decided_role": "admin"}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rs = list(ex.map(lambda _: c.post(f"/api/v1/browser-approvals/requests/{aid}/approve", json=dec), range(4)))
    assert sorted(r.status_code for r in rs) == [200, 409, 409, 409]
    lines = [json.loads(ln) for ln in store.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [r["approval_status"] for r in lines] == ["PENDING", "APPROVED"]
