from pathlib import Path

from scripts.ops.codebase_layer_audit import (
    AuditIssue,
    ClassifiedFile,
    audit,
    build_residual_audit,
    check_consistency,
    classify_path,
    diff_snapshot,
    find_cycles,
    resolve_import_name,
    validate_config,
)


def test_classify_site_module_layers():
    assert classify_path("scripts/hiworks/router.py")[0] == "L5"
    assert classify_path("scripts/hiworks/mail_batch.py")[0] == "L6"
    assert classify_path("scripts/eum/sales_mail.py")[0] == "L6"


def test_classify_core_layers():
    assert classify_path("scripts/gate.py")[0] == "L2"
    assert classify_path("scripts/web_connector.py")[0] == "L3"
    assert classify_path("scripts/cdp_client.py")[0] == "L4"
    assert classify_path("scripts/cdp_db.py")[0] == "L7"
    assert classify_path("admin-web/src/app/page.tsx")[0] == "L9"
    assert classify_path("agent/excel/workflows.py")[0] == "L10"
    assert classify_path("docs/layer_classification.md")[0] == "L12"


def test_audit_detects_root_python_script():
    rows = [
        ClassifiedFile("loose_script.py", "L4", "generic script automation", 10, 1.0),
    ]
    issues = audit(rows, root=Path("."))
    assert any(issue.code == "ROOT_PY_SCRIPT" for issue in issues)


def test_audit_detects_fat_hiworks_router():
    rows = [
        ClassifiedFile("scripts/hiworks/router.py", "L5", "site module", 13000, 1.0),
    ]
    issues = audit(rows, root=Path("."))
    assert AuditIssue(
        "warn",
        "FAT_SITE_ROUTER",
        "scripts/hiworks/router.py",
        "Hiworks router contains too much logic; split into schemas/gates/explorer/mail/workflows.",
        "L5",
    ) in issues


def test_diff_snapshot_detects_added_modified_deleted():
    prev = {"a.py": (1.0, 10), "b.py": (1.0, 10)}
    cur = {"b.py": (2.0, 10), "c.py": (1.0, 10)}
    assert diff_snapshot(prev, cur) == ["deleted:a.py", "modified:b.py", "added:c.py"]


def test_find_cycles_detects_strong_components():
    graph = {
        "pkg.a": {"pkg.b"},
        "pkg.b": {"pkg.c"},
        "pkg.c": {"pkg.a"},
        "pkg.d": set(),
    }
    assert find_cycles(graph) == [["pkg.a", "pkg.b", "pkg.c"]]


def test_resolve_relative_import_name():
    assert resolve_import_name("pkg.site.router", "schemas", 1) == "pkg.site.schemas"
    assert resolve_import_name("pkg.site.sub.module", "utils", 2) == "pkg.site.utils"


def test_residual_audit_tracks_configured_issue():
    issues = [
        AuditIssue("warn", "CIRCULAR_IMPORT", "pkg.a", "cycle", "L4"),
        AuditIssue("warn", "ROOT_PY_SCRIPT", "x.py", "root", "L4"),
    ]
    config = {
        "tracked_residuals": [
            {"code": "CIRCULAR_IMPORT", "path": "pkg.a", "status": "open"},
            {"code": "FAT_SITE_ROUTER", "path": "scripts/hiworks/router.py", "status": "open"},
        ]
    }
    residual = build_residual_audit(issues, config)
    assert residual["summary"]["tracked_open_count"] == 1
    assert residual["summary"]["resolved_tracked_count"] == 1
    assert residual["summary"]["untracked_warning_count"] == 1


def test_validate_config_accepts_residual_schema():
    checks = validate_config(
        {
            "schema_version": 1,
            "thresholds": {},
            "tracked_residuals": [
                {"code": "X", "path": "pkg.x", "status": "planned"},
            ],
        }
    )
    assert all(check.ok for check in checks)


def test_check_consistency_validates_summary_counts():
    report = {
        "files": [{"path": "a.py", "layer": "L4"}],
        "issues": [{"severity": "warn", "code": "X", "path": "a.py"}],
        "counts": {"L4": 1, "UNKNOWN": 0},
        "summary": {"file_count": 1, "issue_count": 1, "warn_count": 1},
        "schema_validation": {"summary": {"openapi_failed": 0, "pydantic_failed": 0, "document_failed": 0}},
        "circular_imports": {"cycle_count": 0},
    }
    config = {
        "schema_version": 1,
        "thresholds": {
            "max_openapi_failed": 0,
            "max_pydantic_failed": 0,
            "max_document_failed": 0,
            "max_circular_imports": 0,
            "max_unknown_layer_files": 0,
        },
        "tracked_residuals": [],
    }
    result = check_consistency(report, config)
    assert result["ok"] is True
