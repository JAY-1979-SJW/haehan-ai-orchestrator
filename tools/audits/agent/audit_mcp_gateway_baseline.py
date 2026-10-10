from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
BASELINE = ROOT / "docs" / "baseline" / "MCP_GATEWAY_BASELINE.md"
REGISTRY = ROOT / "configs" / "external_mcp_registry.template.json"
APP_BASELINE = ROOT / "docs" / "baseline" / "AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md"
HOME_PAGE = ROOT / "admin-web" / "src" / "app" / "page.tsx"

REQUIRED_BASELINE_TOKENS = [
    "Status: LOCKED",
    "MCP-GATEWAY-BASELINE-01",
    "MCP Gateway",
    "configs/external_mcp_registry.template.json",
    "must not contain",
    "raw tokens",
    "enabled: false",
    "visible result artifact",
    "report path",
    "approval",
]

REQUIRED_APP_TOKENS = [
    "External MCP / Tool Gateway",
    "MCP Gateway readiness",
    "configs/external_mcp_registry.template.json",
    # 2026-10-05: 폐기 확정 문구(현행 사실)도 기준서에 있어야 한다.
    "MCP Gateway surface is retired and is not exposed on the home screen",
    "~~MCP Gateway readiness must be visible in the app",
]

# 2026-10-05: 홈 재작성(855d595a 단일 AI 콘솔) 후 MCP Gateway 표면은 폐기 확정.
# 홈에 이 문구가 다시 나타나면 폐기 정책 위반으로 FAIL(부정 단언).
FORBIDDEN_HOME_TOKENS = [
    "External MCP Gateway",
    "Registered MCP servers and owned app adapters",
    "MCP Gateway readiness",
]

REQUIRED_SERVER_FIELDS = {
    "id",
    "display_name",
    "kind",
    "enabled",
    "owner_app",
    "allowed_tools",
    "blocked_tools",
    "risk_level",
    "read_only_default",
    "approval_required",
    "ui_surface",
    "result_target",
}

SECRET_SHAPED = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]+|password\s*[:=]|secret\s*[:=]|token\s*[:=])"
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_baseline_tokens(ok, findings):
    baseline_text = BASELINE.read_text(encoding="utf-8")
    for token in REQUIRED_BASELINE_TOKENS:
        if token not in baseline_text:
            ok = False
            findings.append(f"[FAIL] missing MCP baseline token: {token}")
    if all(token in baseline_text for token in REQUIRED_BASELINE_TOKENS):
        findings.append("[PASS] MCP gateway baseline is locked")
    return ok


def _audit_servers(ok, findings):
    data = _load_json(REGISTRY)
    servers = data.get("servers")
    if not isinstance(servers, list) or not servers:
        ok = False
        findings.append("[FAIL] MCP registry template must contain at least one disabled example server")
    else:
        for index, server in enumerate(servers):
            if not isinstance(server, dict):
                ok = False
                findings.append(f"[FAIL] MCP server entry {index} must be an object")
                continue
            missing = sorted(REQUIRED_SERVER_FIELDS - set(server))
            if missing:
                ok = False
                findings.append(f"[FAIL] MCP server {server.get('id', index)} missing fields: {', '.join(missing)}")
            if server.get("enabled") is not False:
                ok = False
                findings.append(f"[FAIL] MCP server {server.get('id', index)} must default to enabled=false")
            if not server.get("allowed_tools"):
                ok = False
                findings.append(f"[FAIL] MCP server {server.get('id', index)} must define allowed_tools")
            if not server.get("blocked_tools"):
                ok = False
                findings.append(f"[FAIL] MCP server {server.get('id', index)} must define blocked_tools")
        if ok:
            findings.append(f"[PASS] MCP registry template defines {len(servers)} disabled server/adapter examples")
    return ok


def _audit_app_tokens(ok, findings):
    app_text = APP_BASELINE.read_text(encoding="utf-8") if APP_BASELINE.exists() else ""
    for token in REQUIRED_APP_TOKENS:
        if token not in app_text:
            ok = False
            findings.append(f"[FAIL] app structure baseline missing MCP token: {token}")
    if all(token in app_text for token in REQUIRED_APP_TOKENS):
        findings.append("[PASS] app structure baseline references MCP gateway")
    return ok


def _audit_home_tokens(ok, findings):
    home_text = HOME_PAGE.read_text(encoding="utf-8") if HOME_PAGE.exists() else ""
    present = [token for token in FORBIDDEN_HOME_TOKENS if token in home_text]
    for token in present:
        ok = False
        findings.append(f"[FAIL] retired MCP gateway surface reappeared on home: {token}")
    if not present:
        findings.append("[PASS] home does not expose retired MCP gateway surface")
    return ok


def audit() -> tuple[bool, list[str]]:
    ok = True
    findings: list[str] = []

    if not BASELINE.exists():
        return False, [f"[FAIL] missing baseline: {BASELINE}"]
    ok = _audit_baseline_tokens(ok, findings)

    if not REGISTRY.exists():
        ok = False
        findings.append(f"[FAIL] missing MCP registry template: {REGISTRY}")
        return ok, findings
    registry_text = REGISTRY.read_text(encoding="utf-8")
    if SECRET_SHAPED.search(registry_text):
        ok = False
        findings.append("[FAIL] MCP registry template contains secret-shaped text")
    else:
        findings.append("[PASS] MCP registry template contains no secret-shaped text")

    ok = _audit_servers(ok, findings)

    ok = _audit_app_tokens(ok, findings)

    ok = _audit_home_tokens(ok, findings)

    return ok, findings


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(finding)
    print("RESULT=" + ("PASS_MCP_GATEWAY_BASELINE" if ok else "FAIL_MCP_GATEWAY_BASELINE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
