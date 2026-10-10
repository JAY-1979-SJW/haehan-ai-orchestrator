"""승인 기록 API 상태 전이 검증 시험 (미존재 404 / 종결 후 재결정 409 / 대기→결정 200).

tmp 경로 + monkeypatch 격리 — 운영 경로·네트워크 미사용.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import ai_orchestrator.browser_tool.approval.approval_record_router as router_mod
from ai_orchestrator.asgi import app

_BASE = "/api/v1/browser-approvals/requests"
_DEC = {"decided_by": "a", "decided_role": "admin"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    import ai_orchestrator.core.config as config

    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    store = tmp_path / "approvals.jsonl"
    monkeypatch.setattr(router_mod, "APPROVAL_RECORD_STORE_PATH", store)
    return TestClient(app), store


def _create(c) -> str:
    body = {
        "workflow_run_id": "wf",
        "workflow_id": "w",
        "action_name": "browser.execute_click",
        "operation_type": "click",
        "requested_by": "u",
        "requested_role": "admin",
    }
    return c.post(_BASE, json=body).json()["approval_id"]


def _records(store) -> list[dict]:
    return [json.loads(ln) for ln in store.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.mark.parametrize("verb", ["approve", "reject"])
def test_unknown_id_is_404_and_nothing_written(client, verb):
    c, store = client
    _create(c)
    r = c.post(f"{_BASE}/appr_nope/{verb}", json=_DEC)
    assert r.status_code == 404
    assert len(_records(store)) == 1


@pytest.mark.parametrize("verb", ["approve", "reject"])
def test_unknown_id_without_store_file_is_404(client, verb):
    c, store = client
    assert c.post(f"{_BASE}/appr_nope/{verb}", json=_DEC).status_code == 404
    assert not store.exists()


def test_pending_to_approved_and_rejected_are_200(client):
    c, _ = client
    a, b = _create(c), _create(c)
    assert c.post(f"{_BASE}/{a}/approve", json=_DEC).json()["approval_status"] == "APPROVED"
    assert c.post(f"{_BASE}/{b}/reject", json=_DEC).json()["approval_status"] == "REJECTED"


@pytest.mark.parametrize(
    ("first", "second", "state"),
    [
        ("approve", "approve", "APPROVED"),
        ("approve", "reject", "APPROVED"),
        ("reject", "approve", "REJECTED"),
        ("reject", "reject", "REJECTED"),
    ],
)
def test_second_decision_is_409_and_not_recorded(client, first, second, state):
    c, store = client
    aid = _create(c)
    assert c.post(f"{_BASE}/{aid}/{first}", json=_DEC).status_code == 200
    r = c.post(f"{_BASE}/{aid}/{second}", json=_DEC)
    assert r.status_code == 409
    assert state in r.json()["detail"]
    records = _records(store)
    assert len(records) == 2
    assert records[-1]["approval_status"] == state
