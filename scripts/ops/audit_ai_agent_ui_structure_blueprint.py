from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "docs" / "baseline" / "AI_AGENT_UI_STRUCTURE_BLUEPRINT.md"
APP_BASELINE = ROOT / "docs" / "baseline" / "AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md"
HOME_PAGE = ROOT / "admin-web" / "src" / "app" / "page.tsx"

REQUIRED_BLUEPRINT_TOKENS = [
    "Status: LOCKED",
    "AI-AGENT-UI-STRUCTURE-BLUEPRINT-01",
    "Primary Layout",
    "Home Dashboard",
    "Tool Surface Template",
    "Result Panel",
    "Approval Panel",
    "Work Record Panel",
    "MCP And External Tool Catalog",
    "Navigation Model",
    "Responsive Behavior",
    "Required States",
    "Development Order",
    "low-input, result-first, approval-gated",
]

REQUIRED_APP_TOKENS = [
    "AI_AGENT_UI_STRUCTURE_BLUEPRINT.md",
    "Tool Surface Template",
    "Result Panel",
]

REQUIRED_HOME_TOKENS = [
    "AI agent UI structure blueprint",
    "docs/baseline/AI_AGENT_UI_STRUCTURE_BLUEPRINT.md",
    "Chat And Result Workspace",
    "Quick Actions And Immediate Results",
    "Current App Tool Surfaces",
]


def audit() -> tuple[bool, list[str]]:
    ok = True
    findings: list[str] = []
    if not BLUEPRINT.exists():
        return False, [f"[FAIL] missing UI blueprint: {BLUEPRINT}"]
    blueprint = BLUEPRINT.read_text(encoding="utf-8")
    for token in REQUIRED_BLUEPRINT_TOKENS:
        if token not in blueprint:
            ok = False
            findings.append(f"[FAIL] missing UI blueprint token: {token}")
    if all(token in blueprint for token in REQUIRED_BLUEPRINT_TOKENS):
        findings.append("[PASS] AI agent UI structure blueprint is locked")

    app_text = APP_BASELINE.read_text(encoding="utf-8") if APP_BASELINE.exists() else ""
    for token in REQUIRED_APP_TOKENS:
        if token not in app_text:
            ok = False
            findings.append(f"[FAIL] app baseline missing UI blueprint token: {token}")
    if all(token in app_text for token in REQUIRED_APP_TOKENS):
        findings.append("[PASS] app baseline references UI structure blueprint")

    home_text = HOME_PAGE.read_text(encoding="utf-8") if HOME_PAGE.exists() else ""
    for token in REQUIRED_HOME_TOKENS:
        if token not in home_text:
            ok = False
            findings.append(f"[FAIL] home dashboard missing UI blueprint token: {token}")
    if all(token in home_text for token in REQUIRED_HOME_TOKENS):
        findings.append("[PASS] home dashboard exposes UI blueprint artifact")

    return ok, findings


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(finding)
    print("RESULT=" + ("PASS_AI_AGENT_UI_STRUCTURE_BLUEPRINT" if ok else "FAIL_AI_AGENT_UI_STRUCTURE_BLUEPRINT"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
