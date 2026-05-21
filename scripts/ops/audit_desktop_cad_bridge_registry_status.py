# -*- coding: utf-8 -*-
"""CAD-DESKTOP-HUB-CAD-BRIDGE-REGISTRY-STATUS-01 정책 감사."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "desktop" / "cad_bridge_registry.py"
SRV = ROOT / "desktop" / "local_server.py"
TEST = ROOT / "tests" / "test_cad_bridge_registry_status.py"

FORBIDDEN_TOKENS = (
    "win32com", "pythoncom", "AutoCAD.Application",
    "GetActiveObject", ".SendCommand(", ".SelectAll(",
    "from sqlalchemy", "import sqlalchemy",
    "from django.db", "import alembic", "from alembic",
    "ALTER TABLE", "DROP TABLE",
)

LIFECYCLE_FORBIDDEN_IN_REGISTRY = (
    "subprocess.Popen", "subprocess.run", "subprocess.call",
    "os.kill(", "taskkill /F", "taskkill -F",
    "Stop-Process", ".terminate()", ".kill()",
    "psutil",
)

CROSS_REPO_FORBIDDEN_IMPORTS = (
    "local_bridge", "app.backend", "app.frontend", "mcp_server",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _scan(text: str, tokens) -> list:
    return [t for t in tokens if t in text]


def _import_modules(src: str) -> list:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                modules.append(a.name)
    return modules


def audit():
    findings: dict = {}

    # 1) 파일 존재
    for p in (REG, SRV, TEST):
        if not p.exists():
            findings.setdefault("_missing_files", []).append(
                str(p.relative_to(ROOT)))
    if findings:
        return {
            "verdict": "FAIL_DESKTOP_CAD_BRIDGE_REGISTRY_STATUS",
            "findings": findings,
        }

    reg_src = _read(REG)
    srv_src = _read(SRV)

    # 2) 기본값 8766, host 127.0.0.1
    defaults_ok = (
        "DEFAULT_CAD_BRIDGE_PORT = 8766" in reg_src
        and 'DEFAULT_CAD_BRIDGE_HOST = "127.0.0.1"' in reg_src
        and "DESKTOP_HUB_PORT = 8765" in reg_src
    )
    if not defaults_ok:
        findings.setdefault("_defaults", []).append(
            "기본 8766 / host 127.0.0.1 / hub 8765 분리 누락")

    # 3) 8001 live 사용 금지 (정책 docstring + FORBIDDEN 상수 선언만 허용)
    forbidden_live_8001 = (
        ":8001", "= 8001", "port=8001", "PORT = 8001", "PORT=8001",
    )
    for token in forbidden_live_8001:
        if token in reg_src:
            findings.setdefault("_8001_live", []).append(token)
    if "8001" in srv_src:
        # local_server 에는 8001 0건
        findings.setdefault("_8001_server", []).append("local_server 에 8001 등장")

    # 4) CAD repo 모듈 직접 import 금지
    for mod in _import_modules(reg_src):
        for fp in CROSS_REPO_FORBIDDEN_IMPORTS:
            if mod.startswith(fp):
                findings.setdefault("_cad_import", []).append(mod)

    # 5) AutoCAD / DB 토큰 금지 (registry)
    hits = _scan(reg_src, FORBIDDEN_TOKENS)
    if hits:
        findings.setdefault("_forbidden_registry", []).extend(hits)

    # 6) registry 에 process lifecycle 코드 없음
    hits = _scan(reg_src, LIFECYCLE_FORBIDDEN_IN_REGISTRY)
    if hits:
        findings.setdefault("_lifecycle_registry", []).extend(hits)

    # 7) local_server status route 본문에 process kill 없음
    idx = srv_src.find("def get_cad_bridge_status")
    status_route_ok = idx > 0
    if status_route_ok:
        block = srv_src[idx: idx + 800]
        forbidden_in_route = (
            "subprocess.", "Popen(", "os.kill(", "Stop-Process",
            ".terminate(", ".kill(",
        )
        leaks = _scan(block, forbidden_in_route)
        if leaks:
            findings.setdefault("_route_lifecycle", []).extend(leaks)
    else:
        findings.setdefault("_route_missing", []).append(
            "GET /cad/bridge/status route 미등록")

    # 8) /cad/bridge/proxy 라우트는 본 트랙 정책상 아직 미등록.
    # lifecycle start/stop/restart 는 CAD-DESKTOP-HUB-CAD-BRIDGE-LIFECYCLE-01
    # 트랙에서 추가됨 — 본 registry/status audit 은 proxy 부재만 검증.
    forbidden_routes = (
        '"/cad/bridge/proxy', "'/cad/bridge/proxy",
    )
    hits = _scan(srv_src, forbidden_routes)
    if hits:
        findings.setdefault("_proxy_routes_premature", []).extend(hits)

    # 9) status 코드 5종 정의
    required_statuses = (
        "STATUS_NOT_CONFIGURED", "STATUS_STOPPED",
        "STATUS_RUNNING", "STATUS_UNREACHABLE", "STATUS_UNKNOWN",
    )
    statuses_ok = all(s in reg_src for s in required_statuses)
    if not statuses_ok:
        findings.setdefault("_statuses", []).append("5종 status 누락")

    # 10) import 동작 확인
    sys.path.insert(0, str(ROOT))
    try:
        from desktop import cad_bridge_registry as _r  # noqa
        from desktop.local_server import app as _a  # noqa
        import_ok = True
    except Exception as exc:
        import_ok = False
        findings.setdefault("_import", []).append(str(exc))

    verdict = (
        "PASS_DESKTOP_CAD_BRIDGE_REGISTRY_STATUS"
        if (not findings and defaults_ok and status_route_ok
            and statuses_ok and import_ok)
        else "FAIL_DESKTOP_CAD_BRIDGE_REGISTRY_STATUS"
    )
    return {
        "verdict": verdict,
        "defaults_ok": defaults_ok,
        "status_route_ok": status_route_ok,
        "statuses_ok": statuses_ok,
        "import_ok": import_ok,
        "findings": findings,
    }


def main():
    r = audit()
    print(f"[DESKTOP CAD_BRIDGE REGISTRY_STATUS AUDIT] verdict={r['verdict']}")
    if r["verdict"].startswith("PASS"):
        print(
            f"  defaults: {r['defaults_ok']} "
            f"statusRoute: {r['status_route_ok']} "
            f"statuses: {r['statuses_ok']} import: {r['import_ok']}"
        )
    for f, lines in r.get("findings", {}).items():
        print(f"  {f}:")
        for entry in lines:
            print(f"    {entry}")
    return 0 if r["verdict"].startswith("PASS") else 2


if __name__ == "__main__":
    sys.exit(main())
