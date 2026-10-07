"""도구 분리(hiworks) 이동 시험 — API 평면 파일을 connectors/hiworks/ 로 옮겨도 옛 경로·공개 이름·라우트·R2 승인 게이트가 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

BEFORE = json.loads((Path(__file__).parent / "data" / "split_w3c_before.json").read_text(encoding="utf-8"))
MOVED = {
    "hiworks_client": "hiworks.client",
    "hiworks_collectors": "hiworks.collectors",
    "hiworks_config": "hiworks.config",
    "hiworks_mail_router": "hiworks.mail_router",
}


@pytest.mark.parametrize(("old", "new"), MOVED.items())
def test_old_path_is_alias_of_new_module(old, new):
    assert importlib.import_module(f"ai_orchestrator.connectors.{old}") is importlib.import_module(
        f"ai_orchestrator.connectors.{new}"
    )


@pytest.mark.parametrize("old", ["hiworks_client", "hiworks_collectors", "hiworks_config"])
def test_public_names_unchanged(old):
    mod = importlib.import_module(f"ai_orchestrator.connectors.{old}")
    assert sorted(n for n in dir(mod) if not n.startswith("__")) == BEFORE["names"][old]


def test_routes_unchanged():
    router = importlib.import_module("ai_orchestrator.connectors.hiworks.mail_router").hiworks_mail_router
    assert sorted([sorted(r.methods or []), r.path] for r in router.routes) == BEFORE["hw_router"]


def test_inbox_still_reaches_the_reader_after_the_move(monkeypatch):
    """repo_root() 기준이라 이동(깊이 변경) 뒤에도 루트 hiworks_mail_reader.py 를 찾는다(회귀 방지)."""
    import orchestrator_v1.inbox.hiworks_mail_reader as real

    mod = importlib.import_module("ai_orchestrator.connectors.hiworks.mail_router")
    monkeypatch.setattr(real, "fetch_recent_mails", lambda limit=20: [{"subject": "ok"}])
    monkeypatch.setattr(mod, "log_event", lambda *a, **k: None)
    assert mod.api_inbox(limit=3, user={"actor": "a", "role": "admin"})["items"] == [{"subject": "ok"}]


def test_send_gate_survives_the_move():
    """R2: 하이웍스 /send 는 승인 문구 없이는 403(브라우저 접근 전)."""
    from fastapi import HTTPException

    mod = importlib.import_module("ai_orchestrator.connectors.hiworks.mail_router")
    with pytest.raises(HTTPException) as exc:
        mod.api_send(mod.HWMailSendRequest(confirmed=True), user={"actor": "a", "role": "admin"})
    assert exc.value.status_code == 403
