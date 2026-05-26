from scripts.google import live_inputs
from scripts.ops import audit_google_prefill_maturity as audit


def test_google_live_input_coverage_tracks_strict_prefill_maturity() -> None:
    coverage = live_inputs.build_live_input_coverage()

    assert coverage["counts"]["approval_actions"] == 46
    assert coverage["counts"]["live_input_supported"] == 46
    assert coverage["counts"]["domain_specific_prefill"] == 5
    assert coverage["counts"]["generic_handoff"] == 37
    assert coverage["counts"]["partial_handoff"] == 4
    assert coverage["counts"]["strict_prefill_gaps"] == 41


def test_google_prefill_maturity_marks_generic_handoff_as_gap() -> None:
    report = audit.build_report()
    gaps = {item["action_key"]: item for item in report["strict_prefill_gaps"]}

    assert report["ok"] is False
    assert report["status"] == "strict_prefill_gaps_detected"
    assert gaps["cloud_create_api_credential"]["prefill_maturity"] == "partial_handoff_needs_domain_prefill"
    assert gaps["ai_studio_create_api_key"]["prefill_maturity"] == "partial_handoff_needs_domain_prefill"
    assert gaps["cloud_run_deploy_service"]["prefill_maturity"] == "generic_handoff_needs_domain_prefill"
    assert {item["action_key"] for item in report["priority_gaps"]} == {
        "cloud_create_api_credential",
        "ai_studio_create_api_key",
    }


def test_google_prefill_maturity_default_cli_does_not_fail_on_known_gaps() -> None:
    assert audit.main([]) == 0


def test_google_prefill_maturity_can_fail_when_used_as_strict_gate() -> None:
    assert audit.main(["--fail-on-gaps"]) == 1
