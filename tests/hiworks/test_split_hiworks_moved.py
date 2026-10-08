"""도구 분리(hiworks) 이동 시험 — API 평면 파일을 connectors/hiworks/ 로 옮겨도 옛 경로·공개 이름·라우트·R2 승인 게이트가 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

BEFORE = json.loads((Path(__file__).parent.parent / "data" / "split_w3c_before.json").read_text(encoding="utf-8"))
# 옛 경로 shim(client·collectors·config: SHIM_CLEANUP_1, mail_router: SHIM_CLEANUP_2)은 정리됨 — 새 경로만 확인한다
NEW_NAMES = {"hiworks_client": "hiworks.client", "hiworks_collectors": "hiworks.collectors", "hiworks_config": "hiworks.config"}


@pytest.mark.parametrize("old", ["hiworks_client", "hiworks_collectors", "hiworks_config"])
def test_public_names_unchanged(old):
    mod = importlib.import_module(f"ai_orchestrator.connectors.{NEW_NAMES[old]}")
    assert sorted(n for n in dir(mod) if not n.startswith("__")) == BEFORE["names"][old]


def test_routes_unchanged():
    router = importlib.import_module("ai_orchestrator.connectors.hiworks.mail_router").hiworks_mail_router
    assert sorted([sorted(r.methods or []), r.path] for r in router.routes) == BEFORE["hw_router"]


def test_inbox_still_reaches_the_reader_after_the_move(monkeypatch):
    """라우트가 hiworks_mail_reader 를 정적으로 import 해 이동 뒤에도 실제 모듈의 fetch_recent_mails 를 쓴다(회귀 방지)."""
    import orchestrator_v1.inbox.hiworks_mail_reader as real
    import ai_orchestrator.connectors.hiworks.mail_router as mod
    monkeypatch.setattr(real, "fetch_recent_mails", lambda limit=20: [{"subject": "ok"}])
    monkeypatch.setattr(mod, "log_event", lambda *a, **k: None)
    assert mod.api_inbox(limit=3, user={"actor": "a", "role": "admin"})["items"] == [{"subject": "ok"}]


def test_send_gate_survives_the_move():
    """R2: 하이웍스 /send 는 승인 문구 없이는 403(브라우저 접근 전)."""
    from fastapi import HTTPException
    import ai_orchestrator.connectors.hiworks.mail_router as mod
    with pytest.raises(HTTPException) as exc:
        mod.api_send(mod.HWMailSendRequest(confirmed=True), user={"actor": "a", "role": "admin"})
    assert exc.value.status_code == 403
