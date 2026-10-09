from __future__ import annotations

from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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
    # 2026-10-07 화면 개편(단일 AI 콘솔) 반영: 홈 소스(admin-web/src/app/page.tsx)에 실제 있는 문구로 현행화(개수 5개 유지)
    "단일 AI 작업 콘솔",
    'data-testid="ai-agent-console"',
    "UniversalChat",
    "Haehan AI 콘솔",
    "AI에게 작업을 요청하세요",
]


def _check_tokens(text: str, tokens: list[str], missing_msg: str, pass_msg: str) -> tuple[bool, list[str]]:
    """공통 토큰 검사(2026-09-29 STD-08 분리) — 없는 토큰마다 실패 기록, 전부 있으면 PASS 1건."""
    ok = True
    findings: list[str] = []
    for token in tokens:
        if token not in text:
            ok = False
            findings.append(f"[FAIL] {missing_msg}: {token}")
    if all(token in text for token in tokens):
        findings.append(f"[PASS] {pass_msg}")
    return ok, findings


def audit() -> tuple[bool, list[str]]:
    if not BLUEPRINT.exists():
        return False, [f"[FAIL] missing UI blueprint: {BLUEPRINT}"]
    blueprint = BLUEPRINT.read_text(encoding="utf-8")
    ok1, f1 = _check_tokens(
        blueprint, REQUIRED_BLUEPRINT_TOKENS, "missing UI blueprint token", "AI agent UI structure blueprint is locked"
    )

    app_text = APP_BASELINE.read_text(encoding="utf-8") if APP_BASELINE.exists() else ""
    ok2, f2 = _check_tokens(
        app_text,
        REQUIRED_APP_TOKENS,
        "app baseline missing UI blueprint token",
        "app baseline references UI structure blueprint",
    )

    home_text = HOME_PAGE.read_text(encoding="utf-8") if HOME_PAGE.exists() else ""
    ok3, f3 = _check_tokens(
        home_text,
        REQUIRED_HOME_TOKENS,
        "home dashboard missing UI blueprint token",
        "home dashboard exposes UI blueprint artifact",
    )

    return ok1 and ok2 and ok3, f1 + f2 + f3


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(finding)
    print("RESULT=" + ("PASS_AI_AGENT_UI_STRUCTURE_BLUEPRINT" if ok else "FAIL_AI_AGENT_UI_STRUCTURE_BLUEPRINT"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
