import uuid
from pathlib import Path

from tools.repo_gates import audit_root_legacy_scripts as audit

ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = ROOT / "tmp" / "test_root_legacy_scripts_audit"


def make_case(name: str) -> Path:
    path = TEST_TMP / f"{name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    return path


def test_current_root_scripts_are_classified():
    findings = audit.audit()

    assert [finding for finding in findings if finding.status == "FAIL"] == []


def test_root_script_inventory_matches_config():
    config = audit.load_config()
    configured = sorted(item["path"] for item in config["scripts"])

    assert configured == audit.root_python_files()


def test_unclassified_root_script_fails():
    case = make_case("unclassified")
    (case / "known.py").write_text("pass\n", encoding="utf-8")
    (case / "new_tool.py").write_text("pass\n", encoding="utf-8")
    config = case / "root_legacy_scripts.json"
    config.write_text(
        """
{
  "schema_version": 1,
  "status": "locked",
  "allowed_categories": ["archive_candidate"],
  "scripts": [
    {"path": "known.py", "category": "archive_candidate", "next_action": "archive"}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    findings = audit.audit(root=case, config_path=config)

    assert any(finding.code == "UNCLASSIFIED_ROOT_SCRIPT" for finding in findings)


def test_invalid_category_fails():
    case = make_case("invalid_category")
    (case / "known.py").write_text("pass\n", encoding="utf-8")
    config = case / "root_legacy_scripts.json"
    config.write_text(
        """
{
  "schema_version": 1,
  "status": "locked",
  "allowed_categories": ["archive_candidate"],
  "scripts": [
    {"path": "known.py", "category": "unknown", "next_action": "archive"}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    findings = audit.audit(root=case, config_path=config)

    assert any(finding.code == "INVALID_CATEGORY" for finding in findings)
