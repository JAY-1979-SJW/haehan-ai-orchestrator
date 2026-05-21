"""DESKTOP_WEBVIEW_RELEASE_INSTALL_01 — 배포 zip 생성 + 설치 smoke audit.

실행:
    python scripts/ops/audit_desktop_webview_release_install.py

산출물:
    dist/HaehanAI-Desktop-YYYYMMDD.zip
    data/inspection/desktop_webview_release_install/build_report.json
    data/inspection/desktop_webview_release_install/runtime_smoke_report.json
    data/inspection/desktop_webview_release_install/checksums.json

보안: secret/env/token 파일 bundle 금지.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "data" / "inspection" / "desktop_webview_release_install"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DIST_DIR = ROOT / "dist" / "HaehanAI-Desktop"
BASE_URL = "http://127.0.0.1:8765"

_SECRET_RE = re.compile(
    r"(device_token|registration_code|api[_\-]?key|authorization|cookie|session|password|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_EXCLUDE_PATTERNS = {
    ".env", ".env.local", ".env.production",
    "app.log", "cdp.db", "config.json",
}
_EXCLUDE_DIRS = {"node_modules", "__pycache__", ".git", "build", "src", "playwright"}
# secret 스캔 대상: 설정/환경 파일만 (컴파일된 JS 번들 제외)
_SCAN_EXTENSIONS = {".env", ".ini", ".cfg", ".toml"}
_SCAN_FILENAMES = {"config.json", ".env", "secrets.json", "credentials.json"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


# ── 1. zip 생성 ───────────────────────────────────────────────────────────────


def build_zip() -> dict:
    if not DIST_DIR.exists():
        return {"ok": False, "verdict": "FAIL_EXE_MISSING", "error": "dist/HaehanAI-Desktop 없음"}

    exe = DIST_DIR / "HaehanAI-Desktop.exe"
    if not exe.exists():
        return {"ok": False, "verdict": "FAIL_EXE_MISSING", "error": "HaehanAI-Desktop.exe 없음"}

    date_str = datetime.now().strftime("%Y%m%d")
    zip_name = f"HaehanAI-Desktop-{date_str}.zip"
    zip_path = ROOT / "dist" / zip_name

    included: list[str] = []
    excluded: list[str] = []
    secret_files: list[str] = []

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in DIST_DIR.rglob("*"):
            if not file.is_file():
                continue
            rel = file.relative_to(DIST_DIR)
            parts = rel.parts

            # 제외 디렉터리
            if any(p in _EXCLUDE_DIRS for p in parts[:-1]):
                excluded.append(str(rel))
                continue
            # 제외 파일명
            if file.name in _EXCLUDE_PATTERNS:
                excluded.append(str(rel))
                continue
            # secret 파일 내용 검사 — 설정/환경 파일만 (컴파일 JS 번들 제외)
            if file.suffix in _SCAN_EXTENSIONS or file.name in _SCAN_FILENAMES:
                try:
                    content = file.read_text(encoding="utf-8", errors="ignore")
                    if _has_leak(content):
                        secret_files.append(str(rel))
                        excluded.append(str(rel))
                        continue
                except Exception:
                    pass

            arcname = f"HaehanAI-Desktop/{rel}"
            zf.write(file, arcname)
            included.append(str(rel))

    if secret_files:
        zip_path.unlink(missing_ok=True)
        return {
            "ok": False,
            "verdict": "FAIL_SECRET_LEAK",
            "secret_files": secret_files,
        }

    exe_sha = _sha256(exe)
    zip_sha = _sha256(zip_path)
    zip_size_mb = round(zip_path.stat().st_size / 1024 / 1024, 1)

    checksums = {
        "exe_sha256": exe_sha,
        "zip_sha256": zip_sha,
        "zip_file": zip_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "checksums.json").write_text(
        json.dumps(checksums, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "ok": True,
        "zip_path": str(zip_path.relative_to(ROOT)),
        "zip_name": zip_name,
        "zip_size_mb": zip_size_mb,
        "zip_sha256": zip_sha,
        "exe_sha256": exe_sha,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "verdict": "OK",
    }


# ── 2. 런타임 smoke ───────────────────────────────────────────────────────────


def runtime_smoke() -> dict:
    server_up = _port_up()
    if not server_up:
        return {"ok": False, "verdict": "FAIL_APP_NOT_STARTED", "server_up": False}

    index_code, _ = _get("/")
    status_code, status_body = _get("/agent/status")
    try:
        agent = json.loads(status_body)
    except Exception:
        agent = {}

    ws_ok = False
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
        ws_ok = "101" in resp and "websocket" in resp.lower()
    except Exception:
        pass

    admin_paths = {
        "admin_dashboard": "/proxy/admin/",
        "admin_agents": "/proxy/admin/local-agents",
    }
    admin_results = {}
    for name, path in admin_paths.items():
        code, body = _get(path, timeout=10)
        admin_results[name] = {
            "http_code": code,
            "ok": code in (200, 302, 401, 403),
        }

    return {
        "ok": True,
        "server_up": True,
        "index_200": index_code == 200,
        "ws_101": ws_ok,
        "agent_id": agent.get("agent_id", ""),
        "server_connected": agent.get("server_connected", False),
        "admin_proxy": admin_results,
        "verdict": "OK",
    }


# ── 3. secret leak 검사 ───────────────────────────────────────────────────────


def check_secret_leak(report: dict) -> dict:
    text = json.dumps(report)
    leak = _has_leak(text)
    return {"ok": not leak, "leak_found": leak,
            "verdict": "FAIL_SECRET_LEAK" if leak else "OK"}


# ── main ──────────────────────────────────────────────────────────────────────


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()

    zip_result = build_zip()
    smoke = runtime_smoke()

    exe = DIST_DIR / "HaehanAI-Desktop.exe"
    _internal = DIST_DIR / "_internal"

    report = {
        "run_at": ts,
        "task_id": "DESKTOP_WEBVIEW_RELEASE_INSTALL_01",
        "exe_exists": exe.exists(),
        "internal_exists": _internal.exists(),
        "zip": zip_result,
        "runtime_smoke": smoke,
        "pywebview_entry": (ROOT / "desktop" / "webview_app_pywebview.py").exists(),
        "unsigned_binary": True,
    }

    leak = check_secret_leak(report)
    report["secret_scan"] = leak

    verdicts: list[str] = []
    for r in (zip_result, smoke, leak):
        v = r.get("verdict", "OK")
        if v != "OK":
            verdicts.append(v)

    verdicts.append("WARN_UNSIGNED_BINARY")
    verdicts.append("WARN_INSTALLER_NOT_BUILT")

    verdicts = list(dict.fromkeys(verdicts))
    has_fail = any(v.startswith("FAIL") for v in verdicts)
    final = "FAIL" if has_fail else (
        "PASS_WITH_WARNINGS" if verdicts else "PASS_DESKTOP_WEBVIEW_RELEASE_INSTALL"
    )

    report["verdicts"] = verdicts
    report["final_verdict"] = final

    (OUT_DIR / "runtime_smoke_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "build_report.json").write_text(
        json.dumps({"run_at": ts, "zip": zip_result, "exe_sha256": zip_result.get("exe_sha256", "")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return report


def main() -> int:
    print("DESKTOP_WEBVIEW_RELEASE_INSTALL_01 audit 시작...")
    report = run_audit()
    print(f"\n최종 판정: {report['final_verdict']}")
    for v in report.get("verdicts", []):
        print(f"  {'⚠️' if v.startswith('WARN') else '❌'} {v}")
    zip_r = report.get("zip", {})
    if zip_r.get("ok"):
        print(f"\n  zip: {zip_r.get('zip_name')} ({zip_r.get('zip_size_mb')}MB)")
        print(f"  exe SHA256: {zip_r.get('exe_sha256','')[:32]}…")
        print(f"  zip SHA256: {zip_r.get('zip_sha256','')[:32]}…")
    print(f"\n산출물: {OUT_DIR}")
    return 1 if any(v.startswith("FAIL") for v in report.get("verdicts", [])) else 0


if __name__ == "__main__":
    sys.exit(main())
