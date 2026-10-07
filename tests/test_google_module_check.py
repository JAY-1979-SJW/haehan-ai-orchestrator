from __future__ import annotations

import json

from scripts.google import module_check
from scripts.google import router as google_router
from scripts.google import work_records
from scripts.google.module_contracts import GOOGLE_TOP_MODULE, SUBMODULE_OWNERS
from scripts.google.module_index_builder import build_google_module_index


def test_google_module_index_has_top_manager_and_submodules(tmp_path) -> None:
    payload = module_check.build_google_module_index()

    assert payload["ok"] is True
    assert payload["site"] == "google"
    assert payload["top_module"]["key"] == "google_manager"
    assert payload["submodule_count"] == 10
    assert payload["domain_module_count"] == 50
    assert payload["page_tab_module_count"] == 185
    assert payload["work_action_module_count"] == 96
    assert payload["input_field_module_count"] == 140
    assert payload["final_control_module_count"] == 143
    assert payload["evidence_module_count"] == 96
    assert payload["surface_count"] == 50
    assert payload["checks"]["catalog_matches_taxonomy"] is True
    assert payload["checks"]["all_groups_have_owner"] is True
    assert payload["checks"]["all_owner_modules_exist"] is True
    assert payload["checks"]["all_domain_modules_have_implementation"] is True
    assert payload["checks"]["all_domain_modules_have_page_tabs"] is True
    assert payload["checks"]["all_action_modules_have_domain_module"] is True
    assert payload["checks"]["all_domain_modules_have_read_action"] is True
    assert payload["checks"]["all_page_tab_modules_have_gate"] is True
    assert payload["checks"]["no_input_field_allows_secret_value"] is True
    assert payload["checks"]["no_final_control_allows_ai_click"] is True
    assert payload["checks"]["no_evidence_module_stores_raw_secret"] is True

    by_group = {item["group"]: item for item in payload["submodules"]}
    by_domain = {item["surface_key"]: item for item in payload["domain_modules"]}
    by_page_tab = {item["key"]: item for item in payload["page_tab_modules"]}
    by_action = {item["key"]: item for item in payload["work_action_modules"]}
    by_input = {item["key"]: item for item in payload["input_field_modules"]}
    by_control = {item["key"]: item for item in payload["final_control_modules"]}
    by_evidence = {item["key"]: item for item in payload["evidence_modules"]}
    assert by_group["workspace_productivity"]["module"] == "scripts.google.workspace"
    assert by_group["cloud_backend"]["module"] == "scripts.google.cloud"
    assert by_group["youtube_creator"]["module"] == "scripts.google.youtube"
    assert "gmail" in by_group["workspace_productivity"]["surfaces"]
    assert "cloud_apis_credentials" in by_group["cloud_backend"]["secret_surfaces"]
    assert "youtube_studio" in by_group["youtube_creator"]["approval_surfaces"]
    assert by_domain["gmail"]["implementation_module"] == "scripts.google.workspace.gmail"
    assert by_domain["cloud_apis_credentials"]["implementation_module"] == "scripts.google.cloud.api_credentials"
    assert by_domain["youtube"]["implementation_module"] == "scripts.google.youtube.search"
    assert by_domain["youtube_studio"]["implementation_module"] == "scripts.google.common.youtube_upload"
    assert by_domain["secret_manager"]["secret_tabs"] == ["secrets", "versions"]
    assert by_domain["gmail"]["page_tab_count"] == 5
    assert by_domain["youtube_studio"]["approval_tab_count"] >= 5
    assert "final submit without approval" in by_domain["ads"]["not_allowed"]
    assert by_page_tab["gmail.compose"]["gate"] == "prepare_prefill_only_final_click_user"
    assert by_page_tab["cloud_apis_credentials.credentials"]["gate"] == "explicit_user_approval"
    assert by_page_tab["secret_manager.secrets"]["gate"] == "secret_value_export_blocked"
    assert by_page_tab["youtube.search"]["gate"] == "readonly_allowed"
    assert by_action["gmail_open"]["category"] == "read"
    assert by_action["gmail_send_email"]["gate"] == "explicit_user_approval"
    assert by_action["cloud_create_api_credential"]["approval_phrase"] == "GOOGLE_APPROVED_EXECUTE"
    assert by_input["gmail_send_email.to"]["ai_prefill_allowed"] is True
    assert by_input["cloud_create_api_credential.credential_type"]["user_review_required"] is True
    assert by_input["cloud_create_api_credential.credential_type"]["secret_value_allowed"] is False
    assert by_control["gmail.compose.final_control"]["ai_click_allowed"] is False
    assert by_control["gmail_send_email.final_control"]["user_click_required"] is True
    assert by_evidence["gmail_send_email.evidence"]["store_raw_secret"] is False
    assert "approval_record" in by_evidence["gmail_send_email.evidence"]["required_items"]
    assert "readonly_result_snapshot" in by_evidence["gmail_open.evidence"]["required_items"]

    path = module_check.save_google_module_index(payload, tmp_path / "google_modules.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["submodule_count"] == payload["submodule_count"]
    assert saved["domain_module_count"] == payload["domain_module_count"]
    assert saved["page_tab_module_count"] == payload["page_tab_module_count"]
    assert saved["work_action_module_count"] == payload["work_action_module_count"]
    assert saved["input_field_module_count"] == payload["input_field_module_count"]
    assert saved["final_control_module_count"] == payload["final_control_module_count"]
    assert saved["evidence_module_count"] == payload["evidence_module_count"]


def test_google_router_check_runs_module_index(monkeypatch) -> None:
    saved = {}
    payload = module_check.build_google_module_index()

    monkeypatch.setattr(module_check, "build_google_module_index", lambda: payload)

    def fake_save(report):
        saved["payload"] = report
        return "data/google_module_check_latest.json"

    monkeypatch.setattr(module_check, "save_google_module_index", fake_save)
    monkeypatch.setattr(module_check, "print_google_module_summary", lambda *a, **k: None)
    monkeypatch.setattr(module_check, "record_google_module_check", lambda *a, **k: None)

    google_router.run_google("google", "check", "", [])

    assert saved["payload"]["top_module"]["key"] == "google_manager"


def test_google_work_record_checkpoint_is_lane_separated(tmp_path) -> None:
    record = work_records.checkpoint(
        step="google module test checkpoint",
        command="python scripts/entry/cdp_cli.py google check",
        verification="google work record test passed",
        report="data/google_module_check_latest.json",
        touched=["scripts/google/module_check.py"],
        record_root=tmp_path,
    )

    latest, history = work_records.record_paths(tmp_path)
    saved = json.loads(latest.read_text(encoding="utf-8"))
    entries = work_records.load_history(limit=5, record_root=tmp_path)

    assert record["lane"] == "google"
    assert saved["lane"] == "google"
    assert saved["secret_values_output"] is False
    assert history.exists()
    assert len(entries) == 2
    assert entries[-1]["steps"][-1]["summary"] == "google module test checkpoint"


def test_google_router_records_prints_latest_history(monkeypatch, tmp_path, capsys) -> None:
    work_records.checkpoint(
        step="google router records checkpoint",
        command="python scripts/entry/cdp_cli.py google check",
        record_root=tmp_path,
    )
    monkeypatch.setattr(work_records, "DEFAULT_RECORD_ROOT", tmp_path)

    google_router.run_google("google", "records", "", ["--limit=1"])

    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["lane"] == "google"
    assert len(out["history"]) == 1
    assert out["latest"]["resume_next_step"]

    google_router.run_google("google", "records", "--limit=1", [])
    out = json.loads(capsys.readouterr().out)
    assert len(out["history"]) == 1


def test_google_module_check_is_split_but_public_api_matches() -> None:
    facade_payload = module_check.build_google_module_index()
    builder_payload = build_google_module_index()

    assert GOOGLE_TOP_MODULE["key"] == "google_manager"
    assert "workspace_productivity" in SUBMODULE_OWNERS
    assert facade_payload["submodule_count"] == builder_payload["submodule_count"]
    assert facade_payload["domain_module_count"] == builder_payload["domain_module_count"]
    assert facade_payload["checks"] == builder_payload["checks"]
