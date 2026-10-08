import json

import pytest

from scripts.naver.smartstore import actions


def test_action_catalog_has_read_prepare_and_approval_sections():
    catalog = actions.build_action_catalog()
    sections = {section["name"]: section for section in catalog["sections"]}

    assert set(sections) == {"read", "prepare", "approval"}
    assert sections["read"]["summary"]["implemented"] >= 1
    assert sections["approval"]["summary"]["approval_gated"] >= 3
    assert catalog["contract"]["submit"].endswith(actions.APPROVAL_CONFIRM_TEXT)


def test_prepare_plan_validates_general_product_and_never_submits():
    plan = actions.build_prepare_plan(
        {"name": "Sample", "price": 1000, "stock": 3},
        product_type="general",
        save_after=True,
        dry_run=True,
    )

    assert plan["validation"]["ok"] is True
    assert plan["approval"]["required"] is True
    assert plan["submit_executed"] is False
    assert plan["saved"] is False


def test_prepare_plan_reports_missing_required_fields():
    plan = actions.build_prepare_plan({"name": "Sample"}, product_type="general")

    assert plan["validation"]["ok"] is False
    assert plan["validation"]["missing"] == ["price", "stock"]


def test_submit_plan_accepts_only_approval_actions():
    actions.save_action_catalog(actions.build_action_catalog())
    plan = actions.build_submit_plan(action_id="product.general.save", approved_by="tester")

    assert plan["approval"]["required"] is True
    assert plan["approval"]["confirm_text_required"] == actions.APPROVAL_CONFIRM_TEXT
    assert plan["submit_executed"] is False

    with pytest.raises(ValueError):
        actions.build_submit_plan(action_id="product.list")


def test_save_records(tmp_path):
    catalog_path = actions.save_action_catalog(actions.build_action_catalog(), tmp_path / "catalog.json")
    plan_path = actions.save_prepare_plan(
        actions.build_prepare_plan({"name": "Sample"}, product_type="group"),
        tmp_path / "plan.json",
    )
    record_path = actions.save_submit_record(
        {"workflow": "product_register", "dry_run": True}, tmp_path / "record.json"
    )

    assert json.loads(catalog_path.read_text(encoding="utf-8"))["site_id"] == "smartstore"
    assert json.loads(plan_path.read_text(encoding="utf-8"))["product_type"] == "group"
    assert json.loads(record_path.read_text(encoding="utf-8"))["workflow"] == "product_register"
