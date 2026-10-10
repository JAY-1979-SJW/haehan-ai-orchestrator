"""도구 분리(gmail) 이동 시험 — API 평면 파일을 connectors/google/ 로 옮겨도 옛 경로·공개 이름·라우트·R2 승인 게이트가 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

BEFORE = json.loads((Path(__file__).parent.parent / "data" / "split_w3c_before.json").read_text(encoding="utf-8"))
# gmail_router 옛 경로 shim 은 정리됨(SHIM_CLEANUP_2) — 새 경로만 확인한다


def test_cdp_reader_public_names_unchanged():
    import ai_orchestrator.connectors.google.gmail_cdp_reader as mod
    assert sorted(n for n in dir(mod) if not n.startswith("__")) == BEFORE["names"]["gmail_cdp_reader"]


def test_routes_unchanged():
    router = importlib.import_module("ai_orchestrator.connectors.google.gmail_router").gmail_router
    after = sorted([sorted(r.methods or []), r.path] for r in router.routes)
    assert after == BEFORE["gm_router"]
    assert len(after) == 6


def test_send_gates_survive_the_move():
    """R2: Gmail 실제 발송(/reply dry_run=False)·/send 는 승인 문구 없이는 403(Gmail API·브라우저 접근 전)."""
    from fastapi import HTTPException
    import ai_orchestrator.connectors.google.gmail_router as g
    user = {"actor": "a", "role": "admin"}
    with pytest.raises(HTTPException) as exc:
        g.api_reply(g.GmailReplyRequest(thread_id="t", to="a@b.c", subject="s", body="b", dry_run=False), user=user)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        g.api_send(g.GmailSendRequest(confirmed=True), user=user)
    assert exc.value.status_code == 403
