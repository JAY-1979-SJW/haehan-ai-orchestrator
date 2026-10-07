"""scripts/google 공용 헬퍼(report_io·browser_tasks) 시험."""

from __future__ import annotations

import json
import re

from scripts.google.common import browser_tasks
from scripts.google.common.report_io import (
    print_report_summary,
    save_json_md_report,
    save_json_with_latest,
)

_STAMP = re.compile(r"_\d{8}_\d{6}\.(json|md)$")


def test_save_json_with_latest_writes_both_copies(tmp_path):
    report_dir = tmp_path / "reports"
    latest = tmp_path / "nested" / "latest.json"

    target = save_json_with_latest({"한글": 1}, report_dir, latest, "google_x")

    assert target.parent == report_dir
    assert target.name.startswith("google_x_") and _STAMP.search(target.name)
    assert target.read_text(encoding="utf-8") == latest.read_text(encoding="utf-8")
    assert "한글" in latest.read_text(encoding="utf-8")


def test_save_json_with_latest_explicit_path_and_ascii(tmp_path):
    latest = tmp_path / "latest.json"
    explicit = tmp_path / "explicit.json"

    assert save_json_with_latest({"k": "한"}, tmp_path / "r", latest, "p", explicit, ensure_ascii=True) == explicit
    assert "\\ud55c" in explicit.read_text(encoding="utf-8")
    assert latest.read_text(encoding="utf-8") == explicit.read_text(encoding="utf-8")


def test_save_json_md_report_same_stamp(tmp_path):
    rendered = []

    def render(report):
        rendered.append(report)
        return "# title\n"

    json_path, md_path = save_json_md_report(
        {"a": 1},
        tmp_path / "data",
        tmp_path / "docs",
        tmp_path / "data" / "latest.json",
        "google_y",
        render,
    )

    assert json_path.stem == md_path.stem
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"a": 1}
    assert md_path.read_text(encoding="utf-8") == "# title\n"
    assert rendered == [{"a": 1}]


def test_print_report_summary(capsys, tmp_path):
    print_report_summary(
        "Title",
        {"x": 1, "y": 2},
        [("x", "x"), ("why", "y")],
        tmp_path / "a.json",
        tmp_path / "a.md",
        tmp_path / "l.json",
    )
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == ["=" * 60, "Title", "=" * 60]
    assert lines[3:5] == ["x: 1", "why: 2"]
    assert lines[5:] == [
        f"json: {tmp_path / 'a.json'}",
        f"markdown: {tmp_path / 'a.md'}",
        f"latest: {tmp_path / 'l.json'}",
    ]


class _Page:
    def __init__(self, log):
        self.log = log

    def evaluate(self, js):
        self.log.append(("eval", js))


def test_run_context_menu_delete_builds_js_and_reports(monkeypatch, capsys):
    log: list = []
    monkeypatch.setattr(browser_tasks, "page_goto", lambda page, url: log.append(("goto", url)))
    monkeypatch.setattr(
        browser_tasks,
        "page_wait_visible",
        lambda page, sel, timeout=None: log.append(("wait", sel, timeout)) or True,
    )
    monkeypatch.setattr(browser_tasks, "page_wait_click", lambda page, sel: log.append(("click", sel)))

    browser_tasks.run_context_menu_delete(
        _Page(log),
        ["a", "b's"],
        browser_tasks.ContextDeleteSpec(
            empty_message="EMPTY",
            heading="Svc 삭제",
            home_url="https://x.test",
            ready_selector="[data-id]",
            ready_timeout=20000,
            candidates_selector="[data-name]",
            match_condition="el.getAttribute('data-name') === {name}",
            menu_selector='[role="menu"]',
            done_message="DONE",
            fail_message="FAIL",
        ),
    )

    js = next(entry[1] for entry in log if entry[0] == "eval")
    assert "document.querySelectorAll('[data-name]')" in js
    assert "el.getAttribute('data-name') === \"a b's\"" in js
    assert log[0] == ("goto", "https://x.test")
    assert log[-1] == ("wait", "[data-id]", 5000)
    assert capsys.readouterr().out == "\n[작업] Svc 삭제: a b's\nDONE\n"


def test_run_context_menu_delete_without_args(capsys):
    browser_tasks.run_context_menu_delete(
        None,
        [],
        browser_tasks.ContextDeleteSpec(
            empty_message="EMPTY",
            heading="h",
            home_url="u",
            ready_selector="r",
            ready_timeout=1,
            candidates_selector="c",
            match_condition="{name}",
            menu_selector="m",
            done_message="d",
            fail_message="f",
        ),
    )
    assert capsys.readouterr().out == "EMPTY\n"
