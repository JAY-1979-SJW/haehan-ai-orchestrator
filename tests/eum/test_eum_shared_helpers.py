"""scripts/eum 공용 헬퍼(form_selectors·report_io·menu_actions.fetch_save_print) 시험."""

from __future__ import annotations

import json

from scripts.eum.form_selectors import (
    analysis_entries,
    field_selectors,
    selector_from_button,
    selector_from_field,
    submit_selectors,
)
from scripts.eum.menu_actions import fetch_save_print
from scripts.eum.report_io import save_json

ANALYSIS = {
    "WEBMAN381M00": {
        "url": "https://eum.cw.or.kr/web/man/WEBMAN381M00",
        "fields": [
            {
                "id": "menuSearchKeyowrd",
                "selector": "#menuSearchKeyowrd",
                "placeholder": "menu",
            },
            {"id": "terminalNo", "label": "Terminal"},
            {"name": "placeAddr", "label": "location"},
            "not-a-dict",
        ],
        "textareas": [{"selector": "textarea#memo", "label": "location memo"}],
        "buttons": [
            {"text": "닫기", "selector": "#close"},
            {"text": "Save", "id": "save"},
            {"text": "Save again", "id": "save"},
        ],
    },
    "other": {"url": "https://eum.cw.or.kr/web/man/WEBMAN382M00"},
    "broken": "not-a-dict",
}


def test_selector_from_field_priority_and_menu_skip():
    assert selector_from_field({"id": "menuSearchKeyword", "selector": "#x"}) is None
    assert selector_from_field({"selector": " #sel ", "id": "a", "name": "b"}) == "#sel"
    assert selector_from_field({"id": "a", "name": "b"}) == "#a"
    assert selector_from_field({"name": "b"}) == "input[name='b']"
    assert selector_from_field({}) is None


def test_selector_from_button_skips_close():
    assert selector_from_button({"text": "Close", "selector": "#c"}) is None
    assert selector_from_button({"text": "닫기", "id": "c"}) is None
    assert selector_from_button({"text": "저장", "selector": "#s", "id": "x"}) == "#s"
    assert selector_from_button({"text": "저장", "id": "x"}) == "#x"
    assert selector_from_button({"text": "저장"}) is None


def test_analysis_entries_matches_key_or_url():
    assert analysis_entries(ANALYSIS, "WEBMAN381M00") == [ANALYSIS["WEBMAN381M00"]]
    assert analysis_entries(ANALYSIS, "WEBMAN382M00") == [ANALYSIS["other"]]
    assert analysis_entries({}, "WEBMAN381M00") == []


def test_field_and_submit_selectors_filter_and_dedupe():
    entries = analysis_entries(ANALYSIS, "WEBMAN381M00")
    assert field_selectors(entries, ["terminal"]) == ["#terminalNo"]
    assert field_selectors(entries, ["LOCATION", ""]) == [
        "input[name='placeAddr']",
        "textarea#memo",
    ]
    assert field_selectors(entries, []) == [
        "#terminalNo",
        "input[name='placeAddr']",
        "textarea#memo",
    ]
    assert submit_selectors(entries) == ["#save"]


def test_save_json_creates_dir_and_honours_path(tmp_path):
    data_dir = tmp_path / "eum"
    out = save_json({"한글": 1}, data_dir, "default.json")
    assert out == data_dir / "default.json"
    assert json.loads(out.read_text(encoding="utf-8")) == {"한글": 1}
    assert "한글" in out.read_text(encoding="utf-8")

    other = tmp_path / "custom.json"
    assert save_json([1], data_dir, "default.json", other) == other
    assert json.loads(other.read_text(encoding="utf-8")) == [1]


def test_fetch_save_print(capsys, tmp_path):
    seen = {}

    def fetch(page):
        seen["page"] = page
        return [{"a": 1}, {"a": 2}]

    def save(records):
        seen["records"] = records
        return tmp_path / "out.json"

    path = fetch_save_print("PAGE", fetch, save, "근로내역테스트")

    assert path == tmp_path / "out.json"
    assert seen == {"page": "PAGE", "records": [{"a": 1}, {"a": 2}]}
    assert capsys.readouterr().out == f"근로내역테스트: 2건 조회 → {tmp_path / 'out.json'}\n"
