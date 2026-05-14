import json

from scripts.eum import work_plan
from scripts.eum.workspace import workflow_for_alias


def test_registration_plan_validates_required_inputs():
    workflow = workflow_for_alias("registration")
    plan = work_plan.build_action_plan(workflow, ["P-001", "D-001", "Seoul"])

    assert plan["valid"] is True
    assert plan["will_submit"] is False
    assert plan["inputs"]["project_code"] == "P-001"
    assert "WEBMAN381M00" == plan["code"]


def test_registration_plan_reports_missing_inputs():
    workflow = workflow_for_alias("registration")
    plan = work_plan.build_action_plan(workflow, ["P-001"])

    assert plan["valid"] is False
    assert "device_id is required" in plan["errors"]
    assert "location is required" in plan["errors"]


def test_deregistration_plan_validates_date():
    workflow = workflow_for_alias("deregistration")
    plan = work_plan.build_action_plan(workflow, ["D-001", "2026/05/12"])

    assert plan["valid"] is False
    assert "date must use YYYY-MM-DD" in plan["errors"]


def test_save_action_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(work_plan, "PLANS_DIR", tmp_path)
    workflow = workflow_for_alias("WEBMAN381M00")
    plan = work_plan.build_action_plan(workflow, ["P-001", "D-001", "Seoul"])

    path = work_plan.save_action_plan(plan)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["workflow_key"] == "device_registration"
    assert path.parent.name == "device_registration"


def test_action_plan_mode_can_be_prepare():
    workflow = workflow_for_alias("registration")
    plan = work_plan.build_action_plan(workflow, ["P-001", "D-001", "Seoul"], mode="prepare")

    assert plan["mode"] == "prepare"
    assert plan["will_submit"] is False
