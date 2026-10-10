"""Read-only audit for the locked app development standard."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STANDARD = ROOT / "docs" / "baseline" / "APP_DEVELOPMENT_STANDARD.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "APP_BASELINE.md"
APP_STRUCTURE = ROOT / "docs" / "architecture" / "APP_STRUCTURE.md"
STANDARD_WORKFLOW = ROOT / "docs" / "baseline" / "STANDARD_WORKFLOW.md"

REQUIRED_STANDARD_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: HAEHAN-APP-DEVELOPMENT-STANDARD-01",
    "The app is a server-first control surface.",
    "## 2.1 User Convenience Standard",
    "The app must be comfortable for a non-developer operator.",
    "What can I safely do next?",
    "## 2.2 Target Users",
    "## 3. Required Navigation",
    "Dashboard",
    "Tasks",
    "Approvals",
    "Agents",
    "Tools",
    "Connections",
    "Audit",
    "Consent",
    "Reports",
    "Settings",
    "## 4. First Screen Standard",
    "The first screen is the operator dashboard, not a marketing landing page.",
    "## 4.1 First-Time User Flow",
    "## 5. Screen Contracts",
    "## 6. API Integration Standard",
    "## 7. Design Standard",
    "## 7.1 Usability Standard",
    "## 7.2 Accessibility And Readability",
    "## 7.3 Responsive Standard",
    "## 8. Security And Privacy Standard",
    "## 8.1 User Trust Standard",
    "## 9. Development Order",
    "## 9.1 Connection And Command Lock",
    "Allowed command classes:",
    "Forbidden command classes:",
    "unknown_tool_execute",
    "## 9.2 Developed Tool Attachment Lock",
    "Only developed and inventoried tools may be attached to the app.",
    "Tools in `legacy`, `deprecated`, `unknown`, `TBD`, or `Lock Needed Queue`",
    "## 10. Verification Standard",
    "python tools/audits/app/audit_app_development_standard.py",
    "## 11. Completion Rule",
    "## 12. User Acceptance Checklist",
)

REQUIRED_REFERENCE_PHRASES = (
    "The app must be developed as a server-first control surface.",
    "The server is the final operational source of truth for HAEHAN.",
    "User Data Contribution Consent Boundary",
    "docs/baseline/APP_DEVELOPMENT_STANDARD.md",
    "The app development standard controls app shell, route, screen, API integration",
    "The app connection and command system is locked",
    "only inventoried `active` or `locked` tools may be attached",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    paths = (STANDARD, APP_BASELINE, APP_STRUCTURE, STANDARD_WORKFLOW)
    missing_paths = [str(path.relative_to(ROOT)) for path in paths if not path.exists()]
    if missing_paths:
        return False, ["missing required path(s): " + ", ".join(missing_paths)]

    standard = STANDARD.read_text(encoding="utf-8", errors="replace")
    app_baseline = APP_BASELINE.read_text(encoding="utf-8", errors="replace")
    app_structure = APP_STRUCTURE.read_text(encoding="utf-8", errors="replace")
    workflow = STANDARD_WORKFLOW.read_text(encoding="utf-8", errors="replace")

    missing = _missing(standard, REQUIRED_STANDARD_PHRASES)
    if missing:
        failures.append("app development standard missing phrase(s): " + ", ".join(missing))

    references = app_baseline + "\n" + app_structure + "\n" + workflow
    missing = _missing(references, REQUIRED_REFERENCE_PHRASES)
    if missing:
        failures.append("app baseline references missing phrase(s): " + ", ".join(missing))

    return not failures, failures or [
        "APP_DEVELOPMENT_STANDARD exists and is locked",
        "required navigation and screen contracts are present",
        "server-first app structure references remain intact",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "APP_DEVELOPMENT_STANDARD")


if __name__ == "__main__":
    raise SystemExit(main())
