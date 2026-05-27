from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "baseline" / "AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md"
NAV = ROOT / "admin-web" / "src" / "lib" / "nav.ts"
HOME_PAGE = ROOT / "admin-web" / "src" / "app" / "page.tsx"


REQUIRED_BASELINE_TOKENS = [
    "Status: LOCKED",
    "AI-AGENT-APP-STRUCTURE-DESIGN-BASELINE-01",
    "Market Research",
    "Google Tools",
    "Naver Tools",
    "SmartStore Tools",
    "Work Automation",
    "Ops",
    "Domain Split Rule",
    "UI Design Rules",
    "Execution And Gate Rules",
    "AI Integration Contract",
    "Low-Input Immediate-Result UX Contract",
    "preset/button first",
    "Natural-language input is an override path",
    "Every major tool surface must expose at least one default view",
    "compact chat/input panel",
    "persistent result panel",
    "Chat must not be the only way",
    "User instruction",
    "AI orchestration",
    "bounded server API or backend task",
    "local agent when browser/file/desktop/session access is required",
    "approval gate before final state-changing action",
    "Do not create a separate domain for a tool by default.",
]

REQUIRED_NAV_KEYS = [
    "home",
    "local-agents",
    "market-research",
    "cad",
    "file-map",
    "browser-approvals",
]

REQUIRED_HOME_TOKENS = [
    'data-testid="ai-agent-app-dashboard"',
    "Server, local agent, app UI, and AI orchestration",
    "Runtime Integration Flow",
    "Current App Tool Surfaces",
    "Quick Actions And Immediate Results",
    "Chat And Result Workspace",
    'data-testid="ai-agent-chat-input"',
    'data-testid="ai-agent-result-panel"',
    "Latest result panel",
    "Button-first action",
    "low-input",
    "natural-language input is the fallback",
    "Operating contract",
    "approval gate",
    "Work records",
]


def audit() -> tuple[bool, list[str]]:
    findings: list[str] = []
    ok = True
    if not BASELINE.exists():
        return False, [f"[FAIL] missing baseline: {BASELINE}"]
    text = BASELINE.read_text(encoding="utf-8")
    for token in REQUIRED_BASELINE_TOKENS:
        if token not in text:
            ok = False
            findings.append(f"[FAIL] missing baseline token: {token}")
    if ok:
        findings.append("[PASS] AI agent app structure/design baseline is locked")

    nav_text = NAV.read_text(encoding="utf-8") if NAV.exists() else ""
    for key in REQUIRED_NAV_KEYS:
        if f'key: "{key}"' not in nav_text:
            ok = False
            findings.append(f"[FAIL] missing nav key: {key}")
    if all(f'key: "{key}"' in nav_text for key in REQUIRED_NAV_KEYS):
        findings.append("[PASS] admin-web navigation contains required app surfaces")

    home_text = HOME_PAGE.read_text(encoding="utf-8") if HOME_PAGE.exists() else ""
    for token in REQUIRED_HOME_TOKENS:
        if token not in home_text:
            ok = False
            findings.append(f"[FAIL] missing home dashboard token: {token}")
    if all(token in home_text for token in REQUIRED_HOME_TOKENS):
        findings.append("[PASS] home dashboard exposes server/local/app/AI operating contract")

    market_page = ROOT / "admin-web" / "src" / "app" / "market-research" / "page.tsx"
    market_api = ROOT / "admin-web" / "src" / "app" / "api" / "market-research" / "run" / "route.ts"
    if not market_page.exists() or not market_api.exists():
        ok = False
        findings.append("[FAIL] Market Research UI/API route missing")
    else:
        findings.append("[PASS] Market Research UI and bounded run API are present")

    return ok, findings


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(finding)
    print("RESULT=" + ("PASS_AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE" if ok else "FAIL_AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
