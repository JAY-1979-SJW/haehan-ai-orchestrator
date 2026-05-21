"""DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01 audit script.

실행:
    python scripts/ops/audit_desktop_webview_local_e2e_smoke.py

산출물:
    data/inspection/desktop_webview_local_e2e_smoke/local_e2e_report.json
    data/inspection/desktop_webview_local_e2e_smoke/local_e2e_summary.md
    data/inspection/desktop_webview_local_e2e_smoke/network_summary.json

보안: device_token / registration_code / API key / cookie / secret 원문 출력 금지.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "data" / "inspection" / "desktop_webview_local_e2e_smoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8765"

_SECRET_PATTERNS = re.compile(
    r"(device_token|registration_code|api[_\-]?key|authorization|cookie|session|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _get(path: str, timeout: int = 5) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def _port_listening(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except Exception:
        return False


def _mask(text: str) -> str:
    return _SECRET_PATTERNS.sub(r"\1=<REDACTED>", text)


def _has_secret_leak(text: str) -> bool:
    return bool(_SECRET_PATTERNS.search(text))


# ── 1. server ────────────────────────────────────────────────────────────────


def check_server() -> dict:
    listening = _port_listening()
    if not listening:
        return {"ok": False, "verdict": "FAIL_LOCAL_SERVER_NOT_LISTENING"}
    status_code, body = _get("/agent/status")
    body = _mask(body)
    try:
        data = json.loads(body)
    except Exception:
        data = {}
    return {
        "ok": status_code == 200,
        "listening": True,
        "status_code": status_code,
        "agent_id_present": bool(data.get("agent_id")),
        "server_connected": data.get("server_connected", False),
        "is_complete": data.get("is_complete", False),
        "verdict": "OK" if status_code == 200 else "FAIL_LOCAL_SERVER_NOT_LISTENING",
    }


# ── 2. React UI asset ─────────────────────────────────────────────────────────


def check_ui_assets() -> dict:
    dist = ROOT / "desktop" / "ui_dist"
    index_html = dist / "index.html"
    assets = list((dist / "assets").glob("index-*.js")) + list((dist / "assets").glob("index-*.css"))

    index_code, _ = _get("/")
    js_ok = css_ok = False
    js_name = css_name = ""
    for a in assets:
        if a.suffix == ".js":
            code, _ = _get(f"/assets/{a.name}")
            js_ok = code == 200
            js_name = a.name
        elif a.suffix == ".css":
            code, _ = _get(f"/assets/{a.name}")
            css_ok = code == 200
            css_name = a.name

    ok = index_html.exists() and js_ok and css_ok and index_code == 200
    return {
        "ok": ok,
        "index_html_exists": index_html.exists(),
        "js_file": js_name,
        "css_file": css_name,
        "index_http": index_code,
        "js_200": js_ok,
        "css_200": css_ok,
        "verdict": "OK" if ok else "FAIL_REACT_UI_NOT_LOADED",
    }


# ── 3. WebSocket endpoint ─────────────────────────────────────────────────────


def check_ws_endpoint() -> dict:
    """HTTP 101 Upgrade 확인 (WS handshake). wscat 없이 소켓 레벨로 확인."""
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect(("127.0.0.1", 8765))
        handshake = (
            "GET /ws/ui HTTP/1.1\r\n"
            "Host: 127.0.0.1:8765\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(handshake.encode())
        resp = s.recv(512).decode("utf-8", errors="replace")
        s.close()
        upgraded = "101" in resp and "websocket" in resp.lower()
        return {
            "ok": upgraded,
            "ws_path": "/ws/ui",
            "http_101": upgraded,
            "verdict": "OK" if upgraded else "FAIL_WS_NOT_CONNECTED",
        }
    except Exception as exc:
        return {"ok": False, "ws_path": "/ws/ui", "error": type(exc).__name__,
                "verdict": "FAIL_WS_NOT_CONNECTED"}


# ── 4. agent status ───────────────────────────────────────────────────────────


def check_agent_status() -> dict:
    code, body = _get("/agent/status")
    body = _mask(body)
    try:
        data = json.loads(body)
    except Exception:
        data = {}
    agent_id = data.get("agent_id", "")
    leak = _has_secret_leak(body)
    ok = code == 200 and bool(agent_id) and not leak
    return {
        "ok": ok,
        "http_code": code,
        "agent_id_visible": bool(agent_id),
        "server_connected": data.get("server_connected", False),
        "secret_leak": leak,
        "verdict": "OK" if ok else ("FAIL_SECRET_LEAK" if leak else "FAIL_AGENT_STATUS_NOT_VISIBLE"),
    }


# ── 5. panel smoke ────────────────────────────────────────────────────────────


def check_panels() -> dict:
    panels = [
        ("index", "/"),
        ("logs", "/logs"),
        ("agent_status", "/agent/status"),
        ("favicon", "/favicon.svg"),
    ]
    results = {}
    for name, path in panels:
        code, body = _get(path, timeout=8)
        leak = _has_secret_leak(body)
        results[name] = {
            "http_code": code,
            "ok": code in (200, 204) and not leak,
            "secret_leak": leak,
        }
    return results


# ── 6. admin iframe proxy ─────────────────────────────────────────────────────


_ADMIN_PATHS = {
    "admin_dashboard": "/proxy/admin/",
    "admin_ops": "/proxy/admin/ops",
    "admin_approvals": "/proxy/admin/browser-approvals",
    "admin_agents": "/proxy/admin/local-agents",
    "admin_cad": "/proxy/admin/cad",
}


def check_admin_proxy() -> dict:
    results = {}
    for name, path in _ADMIN_PATHS.items():
        code, body = _get(path, timeout=10)
        leak = _has_secret_leak(body)
        ok_code = code in (200, 302, 401, 403)  # auth 필요도 정상 응답
        broken = code in (0, 500, 502, 503)
        results[name] = {
            "path": path,
            "http_code": code,
            "ok": ok_code and not leak,
            "broken": broken,
            "auth_required": code in (401, 403),
            "secret_leak": leak,
            "verdict": (
                "FAIL_ADMIN_PROXY_BROKEN" if broken
                else "WARN_ADMIN_IFRAME_AUTH_REQUIRED" if code in (401, 403)
                else "OK" if ok_code else "FAIL_ADMIN_PROXY_BROKEN"
            ),
        }
    return results


# ── 7. pywebview smoke ────────────────────────────────────────────────────────


def check_pywebview() -> dict:
    try:
        import webview  # noqa: F401
        installed = True
    except ImportError:
        return {"ok": False, "installed": False, "verdict": "WARN_PYWEBVIEW_NOT_INSTALLED"}

    entry = ROOT / "desktop" / "webview_app_pywebview.py"
    return {
        "ok": True,
        "installed": True,
        "entry_exists": entry.exists(),
        "entry_path": str(entry.relative_to(ROOT)),
        "verdict": "OK" if entry.exists() else "WARN_PYWEBVIEW_NOT_INSTALLED",
    }


# ── 8. secret leak scan ───────────────────────────────────────────────────────


def check_secret_leaks(all_results: dict) -> dict:
    text = json.dumps(all_results)
    leak = _has_secret_leak(text)
    return {
        "ok": not leak,
        "leak_found": leak,
        "verdict": "FAIL_SECRET_LEAK" if leak else "OK",
    }


# ── ui_dist dirty check ───────────────────────────────────────────────────────


def check_ui_dist_dirty() -> dict:
    dist = ROOT / "desktop" / "ui_dist"
    src = ROOT / "desktop" / "ui" / "src"
    dirty = not dist.exists() or not (dist / "index.html").exists()
    return {
        "dist_exists": dist.exists(),
        "src_exists": src.exists(),
        "verdict": "WARN_UI_DIST_DIRTY" if dirty else "OK",
    }


# ── lifecycle smoke ───────────────────────────────────────────────────────────


def check_lifecycle() -> dict:
    """현재 서버 기동 확인 + health endpoint."""
    up = _port_listening()
    health_code, _ = _get("/agent/status")
    return {
        "server_up": up,
        "health_ok": health_code == 200,
        "restart_command": "python -m uvicorn desktop.local_server:app --host 127.0.0.1 --port 8765",
        "verdict": "OK" if up and health_code == 200 else "FAIL_LOCAL_SERVER_NOT_LISTENING",
    }


# ── main ──────────────────────────────────────────────────────────────────────


def run_smoke() -> dict:
    ts = datetime.now(timezone.utc).isoformat()

    server = check_server()
    ui = check_ui_assets()
    ws = check_ws_endpoint()
    agent = check_agent_status()
    panels = check_panels()
    admin = check_admin_proxy()
    pywebview = check_pywebview()
    lifecycle = check_lifecycle()
    dist_dirty = check_ui_dist_dirty()

    report = {
        "run_at": ts,
        "task_id": "DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01",
        "server": server,
        "ui_assets": ui,
        "websocket": ws,
        "agent_status": agent,
        "panels": panels,
        "admin_proxy": admin,
        "pywebview": pywebview,
        "lifecycle": lifecycle,
        "ui_dist_dirty": dist_dirty,
    }

    secret_scan = check_secret_leaks(report)
    report["secret_scan"] = secret_scan

    # verdict 집계
    verdicts = []
    for section in (server, ui, ws, agent, pywebview, lifecycle, dist_dirty, secret_scan):
        v = section.get("verdict", "OK")
        if v != "OK":
            verdicts.append(v)
    for name, r in admin.items():
        v = r.get("verdict", "OK")
        if v != "OK":
            verdicts.append(v)
    for name, r in panels.items():
        if not r.get("ok"):
            verdicts.append(f"WARN_PANEL_{name.upper()}")

    # 중복 제거
    verdicts = list(dict.fromkeys(verdicts))
    has_fail = any(v.startswith("FAIL") for v in verdicts)
    has_warn = any(v.startswith("WARN") for v in verdicts)

    if has_fail:
        final_verdict = "FAIL"
    elif has_warn:
        final_verdict = "PASS_WITH_WARNINGS"
    else:
        final_verdict = "PASS_DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE"

    report["verdicts"] = verdicts
    report["final_verdict"] = final_verdict

    return report


def _write_summary(report: dict) -> str:
    ts = report["run_at"]
    verdict = report["final_verdict"]
    verdicts = report.get("verdicts", [])
    s = report["server"]
    ui = report["ui_assets"]
    ws = report["websocket"]
    ag = report["agent_status"]
    pv = report["pywebview"]
    lc = report["lifecycle"]

    lines = [
        f"# DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01 — {ts}",
        "",
        f"## 최종 판정: **{verdict}**",
        "",
        "## 항목별 결과",
        "",
        f"| 항목 | 결과 |",
        f"|------|------|",
        f"| 서버 8765 LISTEN | {'✅' if s.get('listening') else '❌'} |",
        f"| React UI index 200 | {'✅' if ui.get('index_http') == 200 else '❌'} |",
        f"| JS asset 200 | {'✅' if ui.get('js_200') else '❌'} {ui.get('js_file','')} |",
        f"| CSS asset 200 | {'✅' if ui.get('css_200') else '❌'} {ui.get('css_file','')} |",
        f"| WS /ws/ui 101 | {'✅' if ws.get('http_101') else '❌'} |",
        f"| agent_id visible | {'✅' if ag.get('agent_id_visible') else '❌'} |",
        f"| server_connected | {'✅' if ag.get('server_connected') else '❌'} |",
        f"| pywebview 설치 | {'✅' if pv.get('installed') else '⚠️ 미설치'} |",
        f"| webview_app_pywebview.py | {'✅' if pv.get('entry_exists') else '❌'} |",
        f"| lifecycle health | {'✅' if lc.get('health_ok') else '❌'} |",
        f"| secret leak | {'✅ 없음' if not report.get('secret_scan',{}).get('leak_found') else '❌ 발견'} |",
        "",
    ]

    if verdicts:
        lines += ["## WARN/FAIL 목록", ""]
        for v in verdicts:
            lines.append(f"- {v}")
        lines.append("")

    admin_r = report.get("admin_proxy", {})
    lines += ["## Admin Proxy", ""]
    for name, r in admin_r.items():
        icon = "✅" if r.get("ok") else ("⚠️" if r.get("auth_required") else "❌")
        lines.append(f"- {name}: {icon} HTTP {r.get('http_code', 0)}")
    lines.append("")

    lines += [
        "## 실행 명령",
        "",
        "```bash",
        "# 서버 단독",
        "python -m uvicorn desktop.local_server:app --host 127.0.0.1 --port 8765",
        "",
        "# pywebview 앱",
        "python -m desktop.webview_app_pywebview",
        "```",
    ]

    return "\n".join(lines)


def main() -> int:
    print("DESKTOP_WEBVIEW_LOCAL_E2E_SMOKE_01 시작...")
    report = run_smoke()

    # 리포트 저장
    report_path = OUT_DIR / "local_e2e_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = _write_summary(report)
    summary_path = OUT_DIR / "local_e2e_summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    # network summary (admin proxy 결과)
    network = {
        "run_at": report["run_at"],
        "endpoints": {
            "/": report["ui_assets"].get("index_http"),
            "/ws/ui": "101 (WS upgrade)" if report["websocket"].get("http_101") else "FAIL",
            "/agent/status": report["agent_status"].get("http_code"),
            "/logs": report["panels"].get("logs", {}).get("http_code"),
        },
        "admin_proxy": {
            k: {"http_code": v.get("http_code"), "verdict": v.get("verdict")}
            for k, v in report.get("admin_proxy", {}).items()
        },
    }
    (OUT_DIR / "network_summary.json").write_text(
        json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    verdict = report["final_verdict"]
    verdicts = report.get("verdicts", [])
    print(f"\n최종 판정: {verdict}")
    if verdicts:
        for v in verdicts:
            print(f"  {'⚠️' if v.startswith('WARN') else '❌'} {v}")
    print(f"\n리포트: {report_path}")
    print(f"요약:   {summary_path}")

    has_fail = any(v.startswith("FAIL") for v in verdicts)
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
