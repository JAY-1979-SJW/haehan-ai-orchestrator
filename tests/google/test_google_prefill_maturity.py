from scripts.google.common import live_inputs
from tools.audits.google import audit_google_prefill_maturity as audit


def test_google_live_input_coverage_tracks_strict_prefill_maturity() -> None:
    coverage = live_inputs.build_live_input_coverage()

    assert coverage["counts"]["approval_actions"] == 46
    assert coverage["counts"]["live_input_supported"] == 46
    assert coverage["counts"]["domain_specific_prefill"] == 46
    assert coverage["counts"]["generic_handoff"] == 0
    assert coverage["counts"]["partial_handoff"] == 0
    assert coverage["counts"]["strict_prefill_gaps"] == 0


def test_google_prefill_maturity_marks_all_actions_domain_specific_ready() -> None:
    report = audit.build_report()
    ready = {item["action_key"]: item for item in report["domain_specific_prefill"]}

    assert report["ok"] is True
    assert report["status"] == "strict_prefill_complete"
    assert ready["cloud_create_api_credential"]["prefill_maturity"] == "domain_specific_final_approval_ready"
    assert ready["ai_studio_create_api_key"]["prefill_maturity"] == "domain_specific_final_approval_ready"
    assert ready["cloud_run_deploy_service"]["prefill_maturity"] == "domain_specific_final_approval_ready"
    assert ready["play_console_prepare_release"]["prefill_maturity"] == "domain_specific_final_approval_ready"
    assert report["strict_prefill_gaps"] == []
    assert report["priority_gaps"] == []


def test_google_prefill_maturity_default_cli_does_not_fail_on_known_gaps() -> None:
    assert audit.main([]) == 0


def test_google_prefill_maturity_can_fail_when_used_as_strict_gate() -> None:
    assert audit.main(["--fail-on-gaps"]) == 0
