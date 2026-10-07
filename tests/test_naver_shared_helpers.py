"""N6 naver 중복 통합 공용 함수 시험 — 반환값·저장 내용·호출 순서가 통합 전과 같은지 확인."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Page

from scripts.browser.cdp.cdp_helper import CDP
from scripts.common.json_report import save_json_report
from scripts.common.sqlite_helpers import execute_one_change, init_sqlite_schema

# ── scripts/common/sqlite_helpers ────────────────────────────────────


def test_init_sqlite_schema_and_execute_one_change(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    ddl = (
        "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, name TEXT)",
        "CREATE INDEX IF NOT EXISTS ix ON t(name)",
    )
    init_sqlite_schema(db, ddl)
    init_sqlite_schema(db, ddl)  # 두 번째 호출도 오류 없음(IF NOT EXISTS)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO t(name) VALUES ('a')")
    conn.commit()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert {"t", "ix"} <= names
    assert execute_one_change(db, "DELETE FROM t WHERE name = ?", ("a",)) == {"ok": True}
    assert execute_one_change(db, "DELETE FROM t WHERE name = ?", ("a",)) == {"ok": False}


def test_naver_init_db_uses_module_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.naver.blog.management import schedule

    db = tmp_path / "cdp.db"
    monkeypatch.setattr(schedule, "DB_PATH", db)
    schedule._init_db()
    conn = sqlite3.connect(str(db))
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert {"blog_schedule", "idx_blogsch_at"} <= names


# ── scripts/common/json_report ───────────────────────────────────────


def test_save_json_report_default_and_output(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out = save_json_report({"한글": 1}, data_dir, data_dir / "latest.json")
    assert out == data_dir / "latest.json"
    assert out.read_text(encoding="utf-8") == json.dumps({"한글": 1}, ensure_ascii=False, indent=2)
    other = tmp_path / "other.json"
    assert save_json_report([1], data_dir, data_dir / "latest.json", str(other)) == other
    assert json.loads(other.read_text(encoding="utf-8")) == [1]


def test_naver_save_functions_keep_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.naver import keyword_tools

    monkeypatch.setattr(keyword_tools, "DATA_DIR", tmp_path / "d")
    monkeypatch.setattr(keyword_tools, "LATEST_PATH", tmp_path / "d" / "latest.json")
    assert keyword_tools.save_payload({"a": 1}) == tmp_path / "d" / "latest.json"


# ── searchad.keyword_tool.keyword_search_volume ──────────────────────


def test_keyword_search_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.naver.searchad import keyword_tool

    stats = [
        {"keyword": "벽등", "pc_count": 10, "mobile_count": 5, "competition": "low"},
        {"keyword": "간접조명", "pc_count": 100, "mobile_count": 50, "competition": "high"},
    ]
    monkeypatch.setattr(keyword_tool, "get_keyword_stats", lambda keywords: stats)
    rows = keyword_tool.keyword_search_volume([("벽등", 3), ("간접 조명", 7), ("없음", 1)], "ohou_freq")
    assert rows == [
        {"keyword": "간접 조명", "ohou_freq": 7, "pc": 100, "mobile": 50, "total_search": 150, "competition": "high"},
        {"keyword": "벽등", "ohou_freq": 3, "pc": 10, "mobile": 5, "total_search": 15, "competition": "low"},
    ]


# ── marketing.chatgpt_prompt / multichannel._draft ───────────────────


class _FakeCDP:
    def __init__(self, focus: str = "focused") -> None:
        self.focus = focus
        self.calls: list[str] = []

    def js(self, code: str) -> str:
        if "prompt-textarea" in code:
            self.calls.append("focus")
            return self.focus
        self.calls.append("click")
        return "clicked"

    def send(self, method: str, params: dict) -> None:
        self.calls.append(f"{method}:{params['text']}")


def test_send_chatgpt_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.naver.blog.marketing import chatgpt_prompt, gpt_images, gpt_writer

    sleeps: list[float] = []
    monkeypatch.setattr(chatgpt_prompt.time, "sleep", sleeps.append)
    cdp = _FakeCDP()
    assert gpt_images._send_prompt(cast(CDP, cdp), "hi") == "clicked"
    assert cdp.calls == ["focus", "Input.insertText:hi", "click"]
    assert gpt_writer._send_prompt(cast(CDP, _FakeCDP()), "x") == "clicked"
    assert sleeps == [0.3, 0.5, 0.3, 0.8]
    assert gpt_images._send_prompt(cast(CDP, _FakeCDP(focus="textarea not found")), "hi") == "textarea not found"


def test_multichannel_draft_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.naver.blog.marketing import multichannel

    replies: Iterator[dict] = iter([{"ok": True, "text": "  본문  "}, {"ok": False}])

    class FakeAI:
        def _call(self, system: str, prompt: str, max_tokens: int) -> dict:
            return next(replies)

    monkeypatch.setattr(multichannel, "AIResponder", FakeAI)
    assert multichannel.generate_community_answer("질문") == {"ok": True, "answer": "본문"}
    assert multichannel.generate_youtube_script("주제") == {"ok": False}


# ── naver.auth.open_logged_in_page ───────────────────────────────────


class _FakePage:
    def __init__(self) -> None:
        self.visited: list[str] = []

    def goto(self, url: str, timeout: int, wait_until: str) -> None:
        self.visited.append(url)


@pytest.mark.parametrize("login_ok", [True, False])
def test_open_logged_in_page(monkeypatch: pytest.MonkeyPatch, login_ok: bool) -> None:
    from scripts.naver.common import auth
    from scripts.naver.common.mybox import MYBOX_URL, NaverMyBox

    monkeypatch.setattr(auth, "ensure_naver_login", lambda page, return_url: {"ok": login_ok})
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    popups: list[float] = []

    def fake_popups(page, timeout_s: float) -> None:
        popups.append(timeout_s)
        raise RuntimeError("popup fail is ignored")

    monkeypatch.setattr(auth, "handle_page_popups", fake_popups)
    page = _FakePage()
    assert NaverMyBox(cast(Page, page)).open() is login_ok
    assert page.visited == ([MYBOX_URL] if login_ok else [])
    assert popups == ([1.5] if login_ok else [])
