from scripts.eum.workspace import (
    classify_work_risk,
    extract_webman_code,
    known_webman_targets,
    print_workflow_help,
    workflow_for_alias,
)


def test_extract_webman_code_from_mixed_text():
    assert extract_webman_code("go('/web/man/WEBMAN390M00')") == "WEBMAN390M00"
    assert extract_webman_code("none", None) is None


def test_classify_work_risk_marks_approval_pages():
    assert classify_work_risk("device lookup", "WEBMAN390M00") == "read"
    assert classify_work_risk("device registration", "WEBMAN381M00") == "approval"
    assert classify_work_risk("remove request", "WEBMAN382M00") == "approval"


def test_workflow_alias_lookup():
    assert workflow_for_alias("extract")["key"] == "device_inventory"
    assert workflow_for_alias("extract")["auto_execute"] is True
    assert workflow_for_alias("WEBMAN381M00")["risk"] == "approval"
    assert workflow_for_alias("WEBMAN381M00")["auto_execute"] is False
    assert workflow_for_alias("missing") is None


def test_print_workflow_help(capsys):
    assert print_workflow_help("history") is True
    out = capsys.readouterr().out
    assert "python scripts/entry/cdp_cli.py eum history <device_id>" in out
    assert "auto_execute: True" in out

    assert print_workflow_help("missing") is False
    out = capsys.readouterr().out
    assert "Known aliases" in out


def test_known_webman_targets_are_normalized():
    targets = known_webman_targets()
    codes = {target["code"] for target in targets}
    assert "WEBMAN390M00" in codes
    assert all(target["url"].endswith(target["code"]) for target in targets)
