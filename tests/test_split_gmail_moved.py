"""도구 분리(gmail) 이동 시험 — API 평면 파일을 connectors/google/ 로 옮겨도 옛 경로·공개 이름·라우트·R2 승인 게이트가 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

BEFORE = json.loads((Path(__file__).parent / "data" / "split_w3c_before.json").read_text(encoding="utf-8"))
MOVED = {"gmail_cdp_reader": "google.gmail_cdp_reader", "gmail_router": "google.gmail_router"}


@pytest.mark.parametrize(("old", "new"), MOVED.items())
def test_old_path_is_alias_of_new_module(old, new):
    assert importlib.import_module(f"ai_orchestrator.connectors.{old}") is importlib.import_module(
        f"ai_orchestrator.connectors.{new}"
    )


def test_cdp_reader_public_names_unchanged():
    mod = importlib.import_module("ai_orchestrator.connectors.google.gmail_cdp_reader")
    assert sorted(n for n in dir(mod) if not n.startswith("__")) == BEFORE["names"]["gmail_cdp_reader"]


def test_routes_unchanged():
    router = importlib.import_module("ai_orchestrator.connectors.google.gmail_router").gmail_router
    after = sorted([sorted(r.methods or []), r.path] for r in router.routes)
    assert after == BEFORE["gm_router"]
    assert len(after) == 6


def test_send_gates_survive_the_move():
    """R2: Gmail 실제 발송(/reply dry_run=False)·/send 는 승인 문구 없이는 403(Gmail API·브라우저 접근 전)."""
    from fastapi import HTTPException

    g = importlib.import_module("ai_orchestrator.connectors.google.gmail_router")
    user = {"actor": "a", "role": "admin"}
    with pytest.raises(HTTPException) as exc:
        g.api_reply(g.GmailReplyRequest(thread_id="t", to="a@b.c", subject="s", body="b", dry_run=False), user=user)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        g.api_send(g.GmailSendRequest(confirmed=True), user=user)
    assert exc.value.status_code == 403
