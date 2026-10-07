"""N8(instagram overlay)·N11(browser_tool JSONL 읽기) 중복 통합 공용 함수 시험."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.approval.approval_record_store import read_approval_records, read_jsonl_records
from ai_orchestrator.browser_tool.approval.workflow_audit_writer import read_audit_records

# ── browser_tool.approval_record_store.read_jsonl_records ───────────────────────────────────────


def test_read_jsonl_records_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text('{"a": 1}\n\n  \n{"b": 2}\n', encoding="utf-8")
    assert read_jsonl_records(path, "X") == [{"a": 1}, {"b": 2}]
    assert read_approval_records(str(path)) == [{"a": 1}, {"b": 2}]
    assert read_audit_records(path) == [{"a": 1}, {"b": 2}]


def test_read_jsonl_records_missing_file_message(tmp_path: Path) -> None:
    missing = tmp_path / "none.jsonl"
    with pytest.raises(FileNotFoundError, match=r"^Approval file not found: "):
        read_approval_records(missing)
    with pytest.raises(FileNotFoundError, match=r"^Audit file not found: "):
        read_audit_records(missing)


def test_read_jsonl_records_invalid_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"^Invalid JSON at line 2: "):
        read_jsonl_records(path, "X")


# ── instagram overlay ────────────────────────────────────────────────


def test_fit_cover_fills_canvas_for_both_overlays() -> None:
    Image = pytest.importorskip("PIL.Image")
    from scripts.instagram import overlay, reel_overlay

    wide = Image.new("RGB", (3000, 1000))
    tall = Image.new("RGB", (500, 2000))
    for img in (wide, tall):
        assert overlay._fit_cover(img).size == (overlay.W, overlay.H)
        assert reel_overlay._fit_cover(img).size == (reel_overlay.W, reel_overlay.H)
    assert overlay.fit_cover(wide, 100, 50).size == (100, 50)


class _FixedWidthDraw:
    """글자당 폭 10 픽셀로 재는 ImageDraw 흉내."""

    def textlength(self, text: str, font: object = None) -> float:
        return 10.0 * len(text)


def test_wrap_text_shared_by_both_overlays() -> None:
    pytest.importorskip("PIL")
    from scripts.instagram import overlay, reel_overlay

    draw = _FixedWidthDraw()
    assert overlay.wrap_text(draw, "abcdef\ngh", None, 30) == ["abc", "def", "gh"]
    assert overlay._wrap is overlay.wrap_text
    assert reel_overlay._wrap is overlay.wrap_text
