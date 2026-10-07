import json

import pytest

from scripts.hiworks import service_explorer


def test_selected_targets_returns_all_and_specific():
    all_targets = service_explorer.selected_targets("all")
    assert "approval" in all_targets
    assert "hr-work" in all_targets

    one = service_explorer.selected_targets("booking")
    assert list(one) == ["booking"]


def test_selected_targets_rejects_unknown():
    with pytest.raises(KeyError):
        service_explorer.selected_targets("unknown")


def test_save_service_report_writes_json(tmp_path):
    path = service_explorer.save_service_report(
        [{"key": "approval", "label": "전자결재", "surface": {"counts": {"links": 1}}}],
        tmp_path / "report.json",
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["services"][0]["key"] == "approval"
    assert data["services"][0]["surface"]["counts"]["links"] == 1
