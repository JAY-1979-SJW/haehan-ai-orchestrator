from __future__ import annotations

from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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

# 2026-10-05: 홈 재작성(855d595a 단일 AI 콘솔) + nav 정리 이후 현행 값으로 갱신.
# 구조(필수 키/토큰 존재 검사)는 유지, 폐기된 대시보드형 표면 요구만 현행 표면으로 교체.
REQUIRED_NAV_KEYS = [
    "home",
    "ops",
    "mail",
    "hanafax",
    "google",
    "approval",
    "tasks",
]

REQUIRED_HOME_TOKENS = [
    'data-testid="ai-agent-console"',
    "단일 AI 작업 콘솔",
    'import { UniversalChat } from "@/components/chat/UniversalChat"',
    '<UniversalChat domain="default" title="AI 작업 콘솔"',
    "실제 작업은 브라우저(CDP)에서 수행됩니다",
]


def _check_baseline_tokens(text: str) -> tuple[bool, list[str]]:
    ok = True
    findings: list[str] = []
    for token in REQUIRED_BASELINE_TOKENS:
        if token not in text:
            ok = False
            findings.append(f"[FAIL] missing baseline token: {token}")
    if ok:
        findings.append("[PASS] AI agent app structure/design baseline is locked")
    return ok, findings


def _check_nav_keys(nav_text: str) -> tuple[bool, list[str]]:
    ok = True
    findings: list[str] = []
    for key in REQUIRED_NAV_KEYS:
        if f'key: "{key}"' not in nav_text:
            ok = False
            findings.append(f"[FAIL] missing nav key: {key}")
    if all(f'key: "{key}"' in nav_text for key in REQUIRED_NAV_KEYS):
        findings.append("[PASS] admin-web navigation contains required app surfaces")
    return ok, findings


def _check_home_tokens(home_text: str) -> tuple[bool, list[str]]:
    ok = True
    findings: list[str] = []
    for token in REQUIRED_HOME_TOKENS:
        if token not in home_text:
            ok = False
            findings.append(f"[FAIL] missing home console token: {token}")
    if all(token in home_text for token in REQUIRED_HOME_TOKENS):
        findings.append("[PASS] home exposes single AI console (UniversalChat)")
    return ok, findings


def _check_market_research_route(nav_text: str) -> tuple[bool, list[str]]:
    # 2026-10-05: /market-research 페이지가 삭제돼(b769231d) UI/API 존재 요구는 폐기.
    # 대신 nav 가 존재하지 않는 페이지로 링크하지 않는지(404 방지) 검증한다.
    market_page = ROOT / "admin-web" / "src" / "app" / "market-research" / "page.tsx"
    registered = 'href: "/market-research"' in nav_text
    if registered and not market_page.exists():
        return False, ["[FAIL] nav links /market-research but page is missing"]
    return True, ["[PASS] nav does not link to missing Market Research page"]


def audit() -> tuple[bool, list[str]]:
    # 2026-09-29 STD-08 리팩터: 독립 체크 4개를 _check_*() 함수로 분리(순서·조건·문자열 그대로).
    if not BASELINE.exists():
        return False, [f"[FAIL] missing baseline: {BASELINE}"]
    text = BASELINE.read_text(encoding="utf-8")
    ok1, f1 = _check_baseline_tokens(text)

    nav_text = NAV.read_text(encoding="utf-8") if NAV.exists() else ""
    ok2, f2 = _check_nav_keys(nav_text)

    home_text = HOME_PAGE.read_text(encoding="utf-8") if HOME_PAGE.exists() else ""
    ok3, f3 = _check_home_tokens(home_text)

    ok4, f4 = _check_market_research_route(nav_text)

    return ok1 and ok2 and ok3 and ok4, f1 + f2 + f3 + f4


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(finding)
    print(
        "RESULT="
        + ("PASS_AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE" if ok else "FAIL_AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
