import json

import pytest

from scripts.hiworks import actions


def _surface_report():
    return {
        "generated_at": "2026-05-13T00:00:00",
        "services": [
            {
                "key": "approval",
                "label": "approval",
                "target_url": "https://approval.office.hiworks.com/",
                "surface": {
                    "url": "https://approval.office.hiworks.com/",
                    "title": "approval",
                    "counts": {"inputs": 3, "buttons": 3},
                    "inputs": [
                        {"tag": "input", "type": "text", "name": "title", "placeholder": "title", "visible": True},
                        {"tag": "input", "type": "password", "name": "password", "visible": True},
                        {"tag": "input", "type": "file", "name": "attach", "visible": True},
                    ],
                    "buttons": [
                        {"text": "검색", "type": "button", "disabled": False},
                        {"text": "상신", "type": "button", "disabled": False},
                        {"text": "mystery", "type": "button", "disabled": False},
                    ],
                },
            }
        ],
    }


def test_build_action_catalog_classifies_inputs_and_buttons():
    catalog = actions.build_action_catalog(_surface_report())
    service = catalog["services"][0]

    assert service["summary"]["input_total"] == 3
    assert service["summary"]["auto_fillable_inputs"] == 1
    assert service["summary"]["submit_gated_buttons"] == 1
    assert service["summary"]["unknown_gated_buttons"] == 1
    assert service["inputs"][0]["risk"] == "prepare"
    assert service["inputs"][1]["risk"] == "blocked_sensitive"
    assert service["inputs"][2]["risk"] == "blocked_sensitive"
    assert service["buttons"][0]["risk"] == "read"
    assert service["buttons"][1]["risk"] == "submit_gated"


def test_build_prepare_plan_never_submits_and_matches_values():
    catalog = actions.build_action_catalog(_surface_report())
    plan = actions.build_prepare_plan(catalog, service_name="approval", values={"title": "Draft"})
    service = plan["services"][0]

    assert plan["submit_executed"] is False
    assert service["summary"]["values_matched"] == 1
    assert service["summary"]["blocked_inputs"] == 2
    assert service["summary"]["buttons_gated"] == 2
    assert service["button_steps"][1]["action"] == "blocked_until_approval"


def test_build_prepare_plan_rejects_unknown_service():
    catalog = actions.build_action_catalog(_surface_report())

    with pytest.raises(KeyError):
        actions.build_prepare_plan(catalog, service_name="missing")


def test_build_submit_execution_plan_requires_gated_button():
    catalog = actions.build_action_catalog(_surface_report())

    plan = actions.build_submit_execution_plan(
        catalog,
        service_name="approval",
        control_id="approval:button:1",
        approved_by="tester",
        dry_run=True,
    )

    assert plan["approval"]["required"] is True
    assert plan["approval"]["confirm_text_required"] == actions.APPROVAL_CONFIRM_TEXT
    assert plan["control"]["risk"] == "submit_gated"
    assert plan["submit_executed"] is False

    with pytest.raises(ValueError):
        actions.build_submit_execution_plan(
            catalog,
            service_name="approval",
            control_id="approval:button:0",
        )


class _FakePage:
    url = "https://approval.office.hiworks.com/"

    def __init__(self):
        self.payload = None

    def evaluate(self, _script, payload):
        self.payload = payload
        return {
            "ok": True,
            "clicked": not payload["dryRun"],
            "dry_run": payload["dryRun"],
            "matched_text": payload["expectedText"],
            "candidate_count": 3,
        }

    def title(self):
        return "approval"


def test_execute_approved_button_dry_run_does_not_click():
    catalog = actions.build_action_catalog(_surface_report())
    plan = actions.build_submit_execution_plan(catalog, service_name="approval", control_id="approval:button:1")
    page = _FakePage()

    record = actions.execute_approved_button(page, plan, approved=True, dry_run=True)

    assert page.payload["dryRun"] is True
    assert record["result"]["clicked"] is False
    assert record["submit_executed"] is False


def test_execute_approved_button_requires_approval():
    catalog = actions.build_action_catalog(_surface_report())
    plan = actions.build_submit_execution_plan(catalog, service_name="approval", control_id="approval:button:1")

    with pytest.raises(PermissionError):
        actions.execute_approved_button(_FakePage(), plan, approved=False)


def test_save_action_catalog_and_prepare_plan(tmp_path):
    catalog = actions.build_action_catalog(_surface_report())
    catalog_path = actions.save_action_catalog(catalog, tmp_path / "catalog.json")
    plan_path = actions.save_prepare_plan(
        actions.build_prepare_plan(catalog),
        tmp_path / "plan.json",
    )

    assert json.loads(catalog_path.read_text(encoding="utf-8"))["services"][0]["key"] == "approval"
    assert json.loads(plan_path.read_text(encoding="utf-8"))["dry_run"] is True
