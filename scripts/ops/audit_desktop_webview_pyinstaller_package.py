"""DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE_01 audit script.

실행:
    python scripts/ops/audit_desktop_webview_pyinstaller_package.py

산출물:
    data/inspection/desktop_webview_pyinstaller_package/build_report.json
    data/inspection/desktop_webview_pyinstaller_package/runtime_smoke_report.json
    data/inspection/desktop_webview_pyinstaller_package/checksums.json

보안: secret/token/key 원문 출력 금지.
"""
from __future__ import annotations

import json
import re
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "data" / "inspection" / "desktop_webview_pyinstaller_package"
OUT_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "HaehanAI-Desktop"
EXE_ONEDIR = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
EXE_ONEFILE = ROOT / "dist" / f"{APP_NAME}.exe"
UI_DIST = ROOT / "desktop" / "ui_dist"
LAUNCHER = ROOT / "build" / "webview_launcher.py"
BUILD_SCRIPT = ROOT / "scripts" / "build_desktop_webview_app_windows.py"
WEBVIEW_ENTRY = ROOT / "desktop" / "webview_app_pywebview.py"

BASE_URL = "http://127.0.0.1:8765"

_SECRET_RE = re.compile(
    r"(device_token|registration_code|api[_\-]?key|authorization|cookie|session|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def _mask(text: str) -> str:
    return _SECRET_RE.sub(r"\1=<REDACTED>", text)


def _has_leak(text: str) -> bool:
    return bool(_SECRET_RE.search(text))


def _get(path: str, timeout: int = 8) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def _port_up(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except Exception:
        return False


# ── checks ───────────────────────────────────────────────────────────────────


def check_build_artifacts() -> dict:
    exe = EXE_ONEDIR if EXE_ONEDIR.exists() else (EXE_ONEFILE if EXE_ONEFILE.exists() else None)
    ui_ok = (UI_DIST / "index.html").exists()
    launcher_ok = LAUNCHER.exists()
    script_ok = BUILD_SCRIPT.exists()
    entry_ok = WEBVIEW_ENTRY.exists()

    if exe is None:
        return {
            "ok": False,
            "exe_found": False,
            "verdict": "FAIL_EXE_MISSING",
            "ui_dist_ok": ui_ok,
            "launcher_ok": launcher_ok,
            "build_script_ok": script_ok,
            "entry_ok": entry_ok,
        }

    import hashlib
    h = hashlib.sha256()
    with open(exe, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)

    return {
        "ok": True,
        "exe_found": True,
        "exe_path": str(exe.relative_to(ROOT)),
        "exe_size_mb": round(exe.stat().st_size / 1024 / 1024, 1),
        "exe_sha256": h.hexdigest(),
        "unsigned": True,  # code signing 미적용 (WARN_UNSIGNED_BINARY)
        "ui_dist_ok": ui_ok,
        "launcher_ok": launcher_ok,
        "build_script_ok": script_ok,
        "entry_ok": entry_ok,
        "verdict": "OK",
    }


def check_source_artifacts() -> dict:
    """빌드 없이 소스 파일 존재 여부만 확인."""
    ui_ok = (UI_DIST / "index.html").exists()
    js_files = list((UI_DIST / "assets").glob("index-*.js")) if UI_DIST.exists() else []
    css_files = list((UI_DIST / "assets").glob("index-*.css")) if UI_DIST.exists() else []
    return {
        "build_script_exists": BUILD_SCRIPT.exists(),
        "launcher_exists": LAUNCHER.exists(),
        "webview_entry_exists": WEBVIEW_ENTRY.exists(),
        "ui_dist_index_html": ui_ok,
        "ui_dist_js": [f.name for f in js_files],
        "ui_dist_css": [f.name for f in css_files],
        "verdict": "OK" if (BUILD_SCRIPT.exists() and WEBVIEW_ENTRY.exists() and ui_ok) else "FAIL_UI_DIST_MISSING",
    }


def check_build_script_content() -> dict:
    if not BUILD_SCRIPT.exists():
        return {"ok": False, "verdict": "FAIL_BUILD_FAILED"}
    src = BUILD_SCRIPT.read_text(encoding="utf-8")
    checks = {
        "ui_dist_add_data": "add-data" in src and "ui_dist" in src,
        "hidden_import_uvicorn": "uvicorn" in src,
        "hidden_import_webview": "webview" in src,
        "hidden_import_fastapi": "fastapi" in src,
        "hidden_import_websockets": "websockets" in src,
        "collect_submodules_desktop": "desktop" in src,
        "collect_submodules_local_agent": "local_agent" in src,
        "no_secret_in_script": not _has_leak(src),
        "windowed_mode": "windowed" in src,
        "onefolder_default": "onedir" in src,
    }
    ok = all(checks.values())
    return {"ok": ok, "checks": checks, "verdict": "OK" if ok else "WARN_BUILD_SCRIPT_INCOMPLETE"}


def check_runtime_server() -> dict:
    if not _port_up():
        return {"ok": False, "verdict": "FAIL_LOCAL_SERVER_NOT_STARTED", "server_up": False}
    code, body = _get("/agent/status")
    body = _mask(body)
    try:
        data = json.loads(body)
    except Exception:
        data = {}
    leak = _has_leak(body)
    ok = code == 200 and not leak
    return {
        "ok": ok,
        "server_up": True,
        "http_code": code,
        "server_connected": data.get("server_connected", False),
        "agent_id_present": bool(data.get("agent_id")),
        "secret_leak": leak,
        "verdict": "OK" if ok else ("FAIL_SECRET_LEAK" if leak else "FAIL_LOCAL_SERVER_NOT_STARTED"),
    }


def check_runtime_ws() -> dict:
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect(("127.0.0.1", 8765))
        s.sendall(
            b"GET /ws/ui HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n"
            b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            b"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        resp = s.recv(512).decode("utf-8", errors="replace")
        s.close()
        ok = "101" in resp and "websocket" in resp.lower()
        return {"ok": ok, "http_101": ok, "verdict": "OK" if ok else "FAIL_WS_NOT_CONNECTED"}
    except Exception as exc:
        return {"ok": False, "http_101": False, "error": type(exc).__name__,
                "verdict": "FAIL_WS_NOT_CONNECTED"}


def check_runtime_ui() -> dict:
    index_code, _ = _get("/")
    js_ok = css_ok = False
    if UI_DIST.exists():
        for f in (UI_DIST / "assets").glob("index-*.js"):
            code, _ = _get(f"/assets/{f.name}")
            js_ok = code == 200
        for f in (UI_DIST / "assets").glob("index-*.css"):
            code, _ = _get(f"/assets/{f.name}")
            css_ok = code == 200
    ok = index_code == 200 and js_ok and css_ok
    return {
        "ok": ok,
        "index_200": index_code == 200,
        "js_200": js_ok,
        "css_200": css_ok,
        "verdict": "OK" if ok else "FAIL_REACT_UI_NOT_LOADED",
    }


def check_runtime_admin_proxy() -> dict:
    paths = {
        "admin_dashboard": "/proxy/admin/",
        "admin_ops": "/proxy/admin/ops",
        "admin_approvals": "/proxy/admin/browser-approvals",
        "admin_agents": "/proxy/admin/local-agents",
        "admin_cad": "/proxy/admin/cad",
    }
    results = {}
    for name, path in paths.items():
        code, body = _get(path, timeout=10)
        leak = _has_leak(body)
        broken = code in (0, 500, 502, 503)
        ok = code in (200, 302, 401, 403) and not leak
        results[name] = {
            "http_code": code,
            "ok": ok,
            "broken": broken,
            "secret_leak": leak,
            "verdict": "FAIL_ADMIN_PROXY_BROKEN" if broken else
                       "WARN_ADMIN_IFRAME_AUTH_REQUIRED" if code in (401, 403) else
                       "OK" if ok else "FAIL_ADMIN_PROXY_BROKEN",
        }
    return results


def check_pywebview_install() -> dict:
    try:
        import webview  # noqa: F401
        return {"ok": True, "installed": True, "verdict": "OK"}
    except ImportError:
        return {"ok": False, "installed": False, "verdict": "WARN_PYWEBVIEW_NOT_INSTALLED"}


def check_secret_leak(report: dict) -> dict:
    text = _mask(json.dumps(report))
    leak = _has_leak(text)
    return {"ok": not leak, "leak_found": leak,
            "verdict": "FAIL_SECRET_LEAK" if leak else "OK"}


# ── main ──────────────────────────────────────────────────────────────────────


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()

    source = check_source_artifacts()
    build_content = check_build_script_content()
    artifacts = check_build_artifacts()
    server = check_runtime_server()
    ws = check_runtime_ws()
    ui = check_runtime_ui()
    admin = check_runtime_admin_proxy()
    pv = check_pywebview_install()

    report = {
        "run_at": ts,
        "task_id": "DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE_01",
        "source_artifacts": source,
        "build_script_content": build_content,
        "build_artifacts": artifacts,
        "runtime_server": server,
        "runtime_ws": ws,
        "runtime_ui": ui,
        "runtime_admin_proxy": admin,
        "pywebview": pv,
    }

    leak = check_secret_leak(report)
    report["secret_scan"] = leak

    # verdict 집계
    verdicts = []

    def _add(r: dict) -> None:
        v = r.get("verdict", "OK")
        if v != "OK":
            verdicts.append(v)

    for r in (source, build_content, artifacts, server, ws, ui, pv, leak):
        _add(r)

    if not artifacts.get("exe_found"):
        pass  # already in verdicts via artifacts
    if artifacts.get("unsigned"):
        verdicts.append("WARN_UNSIGNED_BINARY")

    for name, r in admin.items():
        _add(r)

    verdicts = list(dict.fromkeys(verdicts))
    has_fail = any(v.startswith("FAIL") for v in verdicts)
    final = ("FAIL" if has_fail
             else "PASS_WITH_WARNINGS" if verdicts
             else "PASS_DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE")

    report["verdicts"] = verdicts
    report["final_verdict"] = final
    return report


def main() -> int:
    print("DESKTOP_WEBVIEW_PYINSTALLER_PACKAGE_01 audit 시작...")
    report = run_audit()

    (OUT_DIR / "runtime_smoke_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n최종 판정: {report['final_verdict']}")
    for v in report.get("verdicts", []):
        prefix = "⚠️" if v.startswith("WARN") else "❌"
        print(f"  {prefix} {v}")
    print(f"\n산출물: {OUT_DIR / 'runtime_smoke_report.json'}")

    return 1 if any(v.startswith("FAIL") for v in report.get("verdicts", [])) else 0


if __name__ == "__main__":
    sys.exit(main())
