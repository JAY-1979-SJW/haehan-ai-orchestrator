# -*- coding: utf-8 -*-
"""CAD-DESKTOP-HUB-CAD-BRIDGE-PROXY-01 정책 감사."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "desktop" / "cad_bridge_proxy.py"
SRV = ROOT / "desktop" / "local_server.py"
TEST = ROOT / "tests" / "test_cad_bridge_proxy.py"

FORBIDDEN_AUTOCAD = (
    "win32com", "pythoncom", "AutoCAD.Application",
    "GetActiveObject", ".SendCommand(", ".SelectAll(",
)
FORBIDDEN_KILL = (
    "subprocess.Popen", "subprocess.run", "subprocess.call",
    "os.system(", "os.kill(", "taskkill /F", "taskkill -F",
    "Stop-Process",
)
FORBIDDEN_EXECUTOR_WIRING = (
    "cad_execute(", "from local_agent.cad.executor",
    "command_executor", "execute_cad_command",
)
CROSS_REPO_FORBIDDEN = (
    "local_bridge", "app.backend", "app.frontend", "mcp_server",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _scan(text, tokens) -> list:
    return [t for t in tokens if t in text]


def _imports(src: str) -> list:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    mods = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.append(n.module)
        elif isinstance(n, ast.Import):
            for a in n.names:
                mods.append(a.name)
    return mods


def audit():
    findings: dict = {}

    for p in (PROXY, SRV, TEST):
        if not p.exists():
            findings.setdefault("_missing_files", []).append(
                str(p.relative_to(ROOT)))
    if findings:
        return {
            "verdict": "FAIL_DESKTOP_CAD_BRIDGE_PROXY",
            "findings": findings,
        }

    proxy_src = _read(PROXY)
    srv_src = _read(SRV)

    # 1) GET/POST /cad/bridge/proxy/{path:path} 등록
    route_ok = (
        '@app.get("/cad/bridge/proxy/{path:path}")' in srv_src
        and '@app.post("/cad/bridge/proxy/{path:path}")' in srv_src
    )
    if not route_ok:
        findings.setdefault("_route", []).append(
            "GET/POST /cad/bridge/proxy/{path:path} 라우트 누락")

    # 2) httpx.AsyncClient 사용
    httpx_ok = "httpx.AsyncClient" in proxy_src
    if not httpx_ok:
        findings.setdefault("_httpx", []).append(
            "httpx.AsyncClient 사용 안 함")

    # 3) allow-list 상수 정의
    allowlist_ok = (
        "POST_ALLOW" in proxy_src
        and "GET_ALLOW" in proxy_src
        and "ALLOWED_METHODS" in proxy_src
    )
    if not allowlist_ok:
        findings.setdefault("_allowlist", []).append("allow-list 상수 누락")

    # 4) mutating 키워드 차단
    mutating_ok = "MUTATING_KEYWORDS" in proxy_src and all(
        kw in proxy_src for kw in (
            "execute", "apply", "mutate", "write", "save",
            "delete", "remove", "update", "approve", "reject",
        )
    )
    if not mutating_ok:
        findings.setdefault("_mutating", []).append(
            "MUTATING_KEYWORDS 누락 또는 부족")

    # 5) AutoCAD/COM 0건
    hits = _scan(proxy_src, FORBIDDEN_AUTOCAD)
    if hits:
        findings.setdefault("_autocad", []).extend(hits)

    # 6) subprocess / kill 0건 (proxy + 새 라우트)
    for p, src in ((PROXY, proxy_src), (SRV, srv_src)):
        hits = _scan(src, FORBIDDEN_KILL)
        if hits:
            findings.setdefault(f"_kill[{p.name}]", []).extend(hits)

    # 7) executor wiring 0건 (proxy)
    hits = _scan(proxy_src, FORBIDDEN_EXECUTOR_WIRING)
    if hits:
        findings.setdefault("_executor_wiring", []).extend(hits)

    # 8) CAD repo 직접 import 0건 (proxy)
    for mod in _imports(proxy_src):
        for fp in CROSS_REPO_FORBIDDEN:
            if mod.startswith(fp):
                findings.setdefault("_cross_repo_import", []).append(mod)

    # 9) 기존 lifecycle route 제거 없음
    lifecycle_kept = all(
        marker in srv_src for marker in (
            '@app.get("/cad/bridge/status")',
            '@app.post("/cad/bridge/start")',
            '@app.post("/cad/bridge/stop")',
            '@app.post("/cad/bridge/restart")',
        )
    )
    if not lifecycle_kept:
        findings.setdefault("_lifecycle_removed", []).append(
            "기존 status/start/stop/restart 라우트 손실")

    # 10) WebSocket cad_bridge_* action 추가 0건
    for ws_action in (
        '"cad_bridge_start"', "'cad_bridge_start'",
        '"cad_bridge_stop"', "'cad_bridge_stop'",
        '"cad_bridge_restart"', "'cad_bridge_restart'",
        '"cad_bridge_proxy"', "'cad_bridge_proxy'",
    ):
        if ws_action in srv_src:
            findings.setdefault("_ws_action_premature", []).append(ws_action)

    # 11) /proxy/admin/ 무손실
    if "/proxy/admin/{path:path}" not in srv_src:
        findings.setdefault("_proxy_admin_lost", []).append(
            "기존 /proxy/admin/ 라우트 손실")

    # 12) 8001 0건
    if "8001" in proxy_src:
        findings.setdefault("_8001", []).append("8001 등장")

    # 13) upstream base 8766 정합
    base_ok = (
        "DEFAULT_CAD_BRIDGE_HOST" in proxy_src
        and "DEFAULT_CAD_BRIDGE_PORT" in proxy_src
    )
    if not base_ok:
        findings.setdefault("_base", []).append(
            "DEFAULT_CAD_BRIDGE_HOST/PORT 사용 안 함")

    # 14) response 에 _source / fallback marker 주입 없음
    forbidden_marker = (
        '"_source"', "'_source'",
        '"_generatedBy"', "'_generatedBy'",
        '"fallback"', "'fallback'",
    )
    # 단, MUTATING_KEYWORDS 의 'fallback' 은 아님 — proxy_src 에서 reject/approve 차단용 등장만 허용
    # _source / _generatedBy 는 0건이어야 함
    for tok in ('"_source"', "'_source'", '"_generatedBy"', "'_generatedBy'"):
        if tok in proxy_src:
            findings.setdefault("_marker_injection", []).append(tok)

    # 15) import 가능
    sys.path.insert(0, str(ROOT))
    try:
        from desktop import cad_bridge_proxy as _p  # noqa
        from desktop.local_server import app as _a  # noqa
        import_ok = True
    except Exception as e:
        import_ok = False
        findings.setdefault("_import", []).append(str(e))

    verdict = (
        "PASS_DESKTOP_CAD_BRIDGE_PROXY"
        if (not findings and route_ok and httpx_ok and allowlist_ok
            and mutating_ok and lifecycle_kept and base_ok and import_ok)
        else "FAIL_DESKTOP_CAD_BRIDGE_PROXY"
    )
    return {
        "verdict": verdict,
        "route_ok": route_ok,
        "httpx_ok": httpx_ok,
        "allowlist_ok": allowlist_ok,
        "mutating_ok": mutating_ok,
        "lifecycle_kept": lifecycle_kept,
        "base_ok": base_ok,
        "import_ok": import_ok,
        "findings": findings,
    }


def main():
    r = audit()
    print(f"[DESKTOP CAD_BRIDGE PROXY AUDIT] verdict={r['verdict']}")
    if r["verdict"].startswith("PASS"):
        print(
            f"  route: {r['route_ok']} httpx: {r['httpx_ok']} "
            f"allowlist: {r['allowlist_ok']} mutating: {r['mutating_ok']} "
            f"lifecycleKept: {r['lifecycle_kept']} base: {r['base_ok']} "
            f"import: {r['import_ok']}"
        )
    for f, lines in r.get("findings", {}).items():
        print(f"  {f}:")
        for entry in lines:
            print(f"    {entry}")
    return 0 if r["verdict"].startswith("PASS") else 2


if __name__ == "__main__":
    sys.exit(main())
