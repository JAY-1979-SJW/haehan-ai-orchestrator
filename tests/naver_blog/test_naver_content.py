import json

import pytest

from scripts.naver.common import content


def _surface_report():
    return {
        "generated_at": "2026-05-13T00:00:00",
        "targets": [
            {
                "key": "cafe",
                "label": "Naver Cafe",
                "target_url": "https://section.cafe.naver.com/",
                "surface": {
                    "url": "https://section.cafe.naver.com/",
                    "title": "cafe",
                    "counts": {"inputs": 2, "buttons": 3},
                    "inputs": [
                        {"tag": "input", "type": "text", "name": "query", "visible": True},
                        {"tag": "input", "type": "password", "name": "password", "visible": True},
                    ],
                    "buttons": [
                        {"index": 0, "text": "검색", "type": "button", "disabled": False},
                        {"index": 1, "text": "등록", "type": "button", "disabled": False},
                        {"index": 2, "text": "unknown", "type": "button", "disabled": False},
                    ],
                },
            }
        ],
    }


def test_select_targets_all_and_specific():
    targets = content.select_targets("all")
    assert "blog" in targets
    assert "cafe" in targets

    assert list(content.select_targets("cafe")) == ["cafe"]

    with pytest.raises(KeyError):
        content.select_targets("missing")


def test_build_action_catalog_classifies_controls():
    catalog = content.build_action_catalog(_surface_report())
    target = catalog["targets"][0]

    assert target["summary"]["input_total"] == 2
    assert target["summary"]["button_total"] == 3
    assert target["summary"]["submit_gated_buttons"] == 1
    assert target["summary"]["unknown_gated_buttons"] == 1
    assert target["inputs"][0]["risk"] == "prepare"
    assert target["inputs"][1]["risk"] == "blocked_sensitive"
    assert target["buttons"][0]["risk"] == "read"
    assert target["buttons"][1]["risk"] == "submit_gated"


def test_build_cafe_write_plan_requires_confirmation_for_publish_shape():
    plan = content.build_cafe_write_plan(
        cafe_url="https://cafe.naver.com/example",
        board_no="1",
        title="Title",
        body="Body",
        publish=True,
        approved_by="tester",
        dry_run=True,
    )

    assert plan["approval"]["required"] is True
    assert plan["approval"]["confirm_text_required"] == content.APPROVAL_CONFIRM_TEXT
    assert plan["dry_run"] is True
    assert plan["published"] is False


def test_save_reports(tmp_path):
    surface_path = content.save_surface_report(_surface_report()["targets"], tmp_path / "surface.json")
    catalog_path = content.save_action_catalog(content.build_action_catalog(_surface_report()), tmp_path / "catalog.json")
    plan_path = content.save_cafe_write_plan(
        content.build_cafe_write_plan(cafe_url="u", board_no="1", title="t", body="b"),
        tmp_path / "plan.json",
    )

    assert json.loads(surface_path.read_text(encoding="utf-8"))["targets"][0]["key"] == "cafe"
    assert json.loads(catalog_path.read_text(encoding="utf-8"))["targets"][0]["key"] == "cafe"
    assert json.loads(plan_path.read_text(encoding="utf-8"))["workflow"] == "cafe_write"
