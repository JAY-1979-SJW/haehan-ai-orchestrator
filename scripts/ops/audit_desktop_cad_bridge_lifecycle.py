# -*- coding: utf-8 -*-
"""CAD-DESKTOP-HUB-CAD-BRIDGE-LIFECYCLE-01 정책 감사."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "desktop" / "cad_bridge_runner.py"
SRV = ROOT / "desktop" / "local_server.py"
REG = ROOT / "desktop" / "cad_bridge_registry.py"
TEST = ROOT / "tests" / "test_cad_bridge_lifecycle.py"

FORBIDDEN_AUTOCAD = (
    "win32com", "pythoncom", "AutoCAD.Application",
    "GetActiveObject", ".SendCommand(", ".SelectAll(",
    "from sqlalchemy", "import sqlalchemy",
    "from django.db", "import alembic", "from alembic",
    "ALTER TABLE", "DROP TABLE",
)

FORBIDDEN_KILL = (
    "os.kill(", "taskkill /F", "taskkill -F",
    "Stop-Process", "psutil.Process",
)

REQUIRED_RUNNER_ROUTES = (
    "/cad/bridge/start", "/cad/bridge/stop", "/cad/bridge/restart",
)

FORBIDDEN_PROXY_ROUTES_THIS_STAGE = (
    "/cad/bridge/proxy",
)

FORBIDDEN_WS_ACTIONS = (
    "cad_bridge_start", "cad_bridge_stop", "cad_bridge_restart",
)

CROSS_REPO_FORBIDDEN = (
    "local_bridge", "app.backend", "app.frontend", "mcp_server",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _scan(text: str, tokens) -> list:
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

    for p in (RUNNER, SRV, REG, TEST):
        if not p.exists():
            findings.setdefault("_missing_files", []).append(
                str(p.relative_to(ROOT)))
    if findings:
        return {
            "verdict": "FAIL_DESKTOP_CAD_BRIDGE_LIFECYCLE",
            "findings": findings,
        }

    runner_src = _read(RUNNER)
    srv_src = _read(SRV)

    # 1) CadBridgeRunner class 존재
    runner_class_ok = "class CadBridgeRunner" in runner_src
    if not runner_class_ok:
        findings.setdefault("_class", []).append("CadBridgeRunner 부재")

    # 2) lifecycle route 3종 등록
    for path in REQUIRED_RUNNER_ROUTES:
        marker = f'@app.post("{path}")'
        if marker not in srv_src:
            findings.setdefault("_route_missing", []).append(path)

    # 3) proxy route 미등록 (이 단계 분리 정책)
    for path in FORBIDDEN_PROXY_ROUTES_THIS_STAGE:
        if path in srv_src:
            findings.setdefault("_proxy_premature", []).append(path)

    # 4) WS action 미등록
    for action in FORBIDDEN_WS_ACTIONS:
        if f'"{action}"' in srv_src or f"'{action}'" in srv_src:
            findings.setdefault("_ws_action_premature", []).append(action)

    # 5) os.kill / taskkill / Stop-Process 0건 (runner + server)
    for p, src in ((RUNNER, runner_src), (SRV, srv_src)):
        hits = _scan(src, FORBIDDEN_KILL)
        if hits:
            findings.setdefault(f"_kill[{p.name}]", []).extend(hits)

    # 6) subprocess.Popen 은 runner 내부로 제한 (server.py 에는 없음)
    if "subprocess.Popen" in srv_src:
        findings.setdefault("_popen_in_server", []).append(
            "local_server.py 에 subprocess.Popen 존재")
    if "subprocess.Popen" not in runner_src:
        findings.setdefault("_popen_missing_in_runner", []).append(
            "cad_bridge_runner.py 에 subprocess.Popen 부재")

    # 7) CAD repo module 직접 import 0건 (runner)
    for mod in _imports(runner_src):
        for fp in CROSS_REPO_FORBIDDEN:
            if mod.startswith(fp):
                findings.setdefault("_cross_repo_import", []).append(mod)

    # 8) AutoCAD/COM/DB 0건 (runner)
    hits = _scan(runner_src, FORBIDDEN_AUTOCAD)
    if hits:
        findings.setdefault("_autocad", []).extend(hits)

    # 9) build_command 검증 — uvicorn local_bridge.server:app + host
    #    127.0.0.1 + port 8766
    cmd_ok = (
        '"-m"' in runner_src
        and '"uvicorn"' in runner_src
        and '"local_bridge.server:app"' in runner_src
        and '"--host"' in runner_src
        and '"--port"' in runner_src
    )
    if not cmd_ok:
        findings.setdefault("_build_command", []).append(
            "uvicorn local_bridge.server:app 명령 구성 누락")

    # 10) 기본 host 127.0.0.1 + 포트 8766 (cad_bridge_registry contract)
    reg_src = _read(REG)
    host_port_ok = (
        'DEFAULT_CAD_BRIDGE_HOST = "127.0.0.1"' in reg_src
        and "DEFAULT_CAD_BRIDGE_PORT = 8766" in reg_src
    )
    if not host_port_ok:
        findings.setdefault("_host_port_contract", []).append(
            "registry contract (host 127.0.0.1 / port 8766) 손상")

    # 11) 8001 0건 (runner)
    forbidden_8001 = (
        ":8001", "= 8001", "port=8001", '"8001"', "'8001'",
    )
    hits = _scan(runner_src, forbidden_8001)
    if hits:
        findings.setdefault("_8001_runner", []).extend(hits)

    # 12) 외부 PID 인자 0건 — 라우트 함수 시그니처에 pid / process_id 가 없음
    forbidden_arg_patterns = (
        "pid: int", "process_id:", "target_pid",
        "def post_cad_bridge_start(pid",
        "def post_cad_bridge_stop(pid",
    )
    hits = _scan(srv_src, forbidden_arg_patterns)
    if hits:
        findings.setdefault("_external_pid_arg", []).extend(hits)

    # 13) singleton 위치 — local_server.py 모듈 변수
    singleton_ok = (
        "_cad_bridge_runner: Optional[CadBridgeRunner]" in srv_src
        and "_get_cad_bridge_runner" in srv_src
    )
    if not singleton_ok:
        findings.setdefault("_singleton", []).append(
            "module-level singleton runner 누락")

    # 14) 별도 desktop/cad_bridge_state.py 미존재 (book of decisions)
    state_file = ROOT / "desktop" / "cad_bridge_state.py"
    if state_file.exists():
        findings.setdefault("_state_file_premature", []).append(
            "desktop/cad_bridge_state.py 가 본 트랙 정책 위반으로 존재")

    # 15) import 가능
    sys.path.insert(0, str(ROOT))
    try:
        from desktop import cad_bridge_runner as _r  # noqa
        from desktop.local_server import app as _a  # noqa
        import_ok = True
    except Exception as exc:
        import_ok = False
        findings.setdefault("_import", []).append(str(exc))

    # 16) runnerState additive — GET /cad/bridge/status 응답에 runnerState 포함
    runner_state_additive = "runnerState" in srv_src
    if not runner_state_additive:
        findings.setdefault("_runner_state_additive", []).append(
            "GET /cad/bridge/status 에 runnerState 필드 추가 안 됨")

    verdict = (
        "PASS_DESKTOP_CAD_BRIDGE_LIFECYCLE"
        if (not findings and runner_class_ok and cmd_ok and host_port_ok
            and singleton_ok and runner_state_additive and import_ok)
        else "FAIL_DESKTOP_CAD_BRIDGE_LIFECYCLE"
    )
    return {
        "verdict": verdict,
        "runner_class_ok": runner_class_ok,
        "cmd_ok": cmd_ok,
        "host_port_ok": host_port_ok,
        "singleton_ok": singleton_ok,
        "runner_state_additive": runner_state_additive,
        "import_ok": import_ok,
        "findings": findings,
    }


def main():
    r = audit()
    print(f"[DESKTOP CAD_BRIDGE LIFECYCLE AUDIT] verdict={r['verdict']}")
    if r["verdict"].startswith("PASS"):
        print(
            f"  runner: {r['runner_class_ok']} cmd: {r['cmd_ok']} "
            f"hostPort: {r['host_port_ok']} singleton: {r['singleton_ok']} "
            f"runnerStateAdditive: {r['runner_state_additive']} "
            f"import: {r['import_ok']}"
        )
    for f, lines in r.get("findings", {}).items():
        print(f"  {f}:")
        for entry in lines:
            print(f"    {entry}")
    return 0 if r["verdict"].startswith("PASS") else 2


if __name__ == "__main__":
    sys.exit(main())
