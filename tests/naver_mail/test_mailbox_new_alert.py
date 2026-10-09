"""새 메일 알림 — 기준서 docs/specs/2026-10-02_mailbox_new_mail_alert.md §6."""

from __future__ import annotations

import json

from ai_orchestrator.connectors.naver_mail import new_policy as pol
from ai_orchestrator.server import mcp_server
from scripts.naver.mail.imap import imap_mailbox as mailbox


class _Conn:
    def __init__(self, line: bytes | None):
        self.line, self.selected = line, False

    def login(self, user, pw):
        return "OK", []

    def status(self, folder, items):
        return "OK", [self.line] if self.line is not None else []

    def select(self, *a, **k):  # 호출되면 안 된다
        self.selected = True
        return "OK", [b"1"]

    def unselect(self):
        pass

    def logout(self):
        pass


def _factory_for(conn):
    return lambda *a, **k: conn


def test_new_since_cases():
    cur = {"uidnext": 110, "uidvalidity": 7}
    assert pol.new_since(None, cur) == {"reset": True, "count": 0}
    assert pol.new_since({"uidnext": 100, "uidvalidity": 7}, cur) == {"reset": False, "count": 10}
    assert pol.new_since({"uidnext": 110, "uidvalidity": 7}, cur) == {"reset": False, "count": 0}
    assert pol.new_since({"uidnext": 100, "uidvalidity": 8}, cur)["reset"] is True
    assert pol.new_since({"uidnext": 200, "uidvalidity": 7}, cur)["reset"] is True


def test_count_label_cap():
    assert pol.count_label(5) == "5"
    assert pol.count_label(100) == "99+"


def test_inbox_status_parses_without_select():
    conn = _Conn(b'"INBOX" (UIDNEXT 161 UIDVALIDITY 1234 UNSEEN 76)')
    got = mailbox.inbox_status("a", password="pw", factory=_factory_for(conn))
    assert got == {"ok": True, "uidnext": 161, "uidvalidity": 1234, "unseen": 76}
    assert conn.selected is False


def test_inbox_status_bad_response():
    got = mailbox.inbox_status("a", password="pw", factory=_factory_for(_Conn(b"garbage")))
    assert got["ok"] is False


def test_checkpoint_untouched(tmp_path, monkeypatch):
    from scripts.naver.mail.imap import reader

    path = reader._checkpoint_path()
    before = path.read_bytes() if path.exists() else None
    mailbox.inbox_status("a", password="pw", factory=_factory_for(_Conn(b'"INBOX" (UIDNEXT 2 UIDVALIDITY 1 UNSEEN 0)')))
    assert (path.read_bytes() if path.exists() else None) == before


def test_ai_registry_has_no_inbox_watch():
    assert not any("inbox-watch" in json.dumps(v) for v in mcp_server.API_REGISTRY.values())
