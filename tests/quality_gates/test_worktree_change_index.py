from tools.devflow import worktree_change_index as wt


def test_parse_porcelain_handles_rename_and_untracked():
    rows = wt.parse_porcelain(
        " M scripts/hiworks/router.py\n"
        "R  old.py -> scripts/archive/old.py\n"
        "?? docs/worktree_management_index.md\n"
    )

    assert rows == [
        (" M", "scripts/hiworks/router.py", ""),
        ("R ", "scripts/archive/old.py", "old.py"),
        ("??", "docs/worktree_management_index.md", ""),
    ]


def test_build_index_groups_by_layer_owner_and_category():
    index = wt.build_index(
        " M scripts/hiworks/router.py\n"
        "?? tests/test_hiworks_run_log.py\n"
        "?? data/runtime.json\n"
    )

    assert index["summary"]["changed_count"] == 3
    assert index["summary"]["by_owner"]["hiworks"] == 1
    assert index["summary"]["by_owner"]["tests"] == 1
    assert index["summary"]["by_category"]["site_automation"] == 1
    assert index["summary"]["by_category"]["test"] == 1
    assert index["summary"]["by_category"]["runtime_artifact"] == 1


def test_index_embeds_operating_rules_and_reference_pack():
    index = wt.build_index("")

    assert "before_new_work" in index["operating_rules"]
    assert any("Generate this worktree index" in rule for rule in index["operating_rules"]["before_new_work"])
    assert any("pre-change dry-run" in rule for rule in index["operating_rules"]["before_new_work"])
    assert "docs/worktree_management_index.md" in index["reference_pack"]
    assert "docs/pre_change_dry_run_policy_20260513.md" in index["reference_pack"]
    assert "tools/devflow/pre_change_dry_run.py" in index["reference_pack"]
    assert "tools/quality/quality_gate.py" in index["reference_pack"]


def test_repo_ignore_file_is_policy_not_active_code():
    index = wt.build_index(" M .gitignore\n")

    change = index["changes"][0]
    assert change["layer"] == "L1"
    assert change["category"] == "contract_or_policy"
    assert change["owner"] == "repo"


def test_root_legacy_probe_is_archive_doc_category():
    index = wt.build_index("?? debug_gmail_buttons.py\n")

    change = index["changes"][0]
    assert change["layer"] == "L12"
    assert change["category"] == "doc_or_archive"
    assert change["owner"] == "repo"


def test_root_legacy_test_is_test_owner():
    index = wt.build_index("?? test_popup_modules.py\n")

    change = index["changes"][0]
    assert change["layer"] == "L11"
    assert change["category"] == "test"
    assert change["owner"] == "tests"
