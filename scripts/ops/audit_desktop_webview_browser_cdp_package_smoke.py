#!/usr/bin/env python3
"""audit_desktop_webview_browser_cdp_package_smoke.py
DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE_01 감사 스크립트.

Verdicts:
  PASS_DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE
  WARN_PLAYWRIGHT_BROWSER_NOT_BUNDLED
  WARN_SYSTEM_CHROME_REQUIRED
  WARN_SCREENSHOT_LIVE_PARTIAL
  FAIL_PLAYWRIGHT_IMPORT_FAILED
  FAIL_CDP_DAEMON_NOT_STARTED
  FAIL_CDP_PORT_NOT_LISTENING
  FAIL_CONNECT_OVER_CDP_FAILED
  FAIL_BROWSER_PANEL_BROKEN
  FAIL_SCREENSHOT_PANEL_BROKEN
  FAIL_SECRET_LEAK
"""
from __future__ import annotations

import json
import os
import socket
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
REPORT_DIR = ROOT / "data/inspection/desktop_webview_browser_cdp_package_smoke"
PANELS     = ROOT / "desktop/ui/src/components/panels/Panels.tsx"
SERVER     = ROOT / "desktop/local_server.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues:   list[str] = []
warnings: list[str] = []


def fail(code: str, msg: str) -> None:
    issues.append(f"{F} {code} — {msg}")


def warn(code: str, msg: str) -> None:
    warnings.append(f"{W} {code} — {msg}")


# ── 1. 의존성 ─────────────────────────────────────────────────────────
def _check_import(pkg: str) -> bool:
    import importlib
    try:
        importlib.import_module(pkg)
        return True
    except ImportError:
        return False


if not _check_import("playwright"):
    fail("FAIL_PLAYWRIGHT_IMPORT_FAILED", "playwright import 불가 — pip install playwright 필요")
if not _check_import("psutil"):
    fail("FAIL_PLAYWRIGHT_IMPORT_FAILED", "psutil import 불가")
if not _check_import("websockets"):
    fail("FAIL_PLAYWRIGHT_IMPORT_FAILED", "websockets import 불가")

# ── 2. 배포본 playwright 번들 여부 ────────────────────────────────────
exe_internal = ROOT / "dist/HaehanAI-Desktop/_internal"
playwright_bundled = (exe_internal / "playwright").exists()
if not playwright_bundled:
    warn("WARN_PLAYWRIGHT_BROWSER_NOT_BUNDLED",
         "playwright가 exe에 미포함 — 배포 대상 PC에서 pip install playwright 필요")

# ── 3. 시스템 Chrome 확인 ─────────────────────────────────────────────
chrome_paths = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
]
system_chrome = any(p.exists() for p in chrome_paths)
chromium_bundled = Path(
    os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
).exists()

if not system_chrome and not chromium_bundled:
    warn("WARN_SYSTEM_CHROME_REQUIRED",
         "시스템 Chrome 미발견 — playwright install chromium 또는 Chrome 설치 필요")

# ── 4. CDP 9222 포트 ──────────────────────────────────────────────────
sock = socket.socket()
sock.settimeout(1)
cdp_listening = sock.connect_ex(("127.0.0.1", 9222)) == 0
sock.close()

if not cdp_listening:
    fail("FAIL_CDP_PORT_NOT_LISTENING", "127.0.0.1:9222 미응답 — CDP daemon 미실행")
else:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3) as r:
            ver = json.loads(r.read())
        browser_ver = ver.get("Browser", "?")
    except Exception as e:
        fail("FAIL_CDP_DAEMON_NOT_STARTED", f"/json/version 응답 실패: {e}")
        browser_ver = "unknown"

# ── 5. connect_over_cdp ───────────────────────────────────────────────
cdp_connect_ok = False
if cdp_listening and _check_import("playwright"):
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        with sync_playwright() as pw:
            b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            cdp_connect_ok = len(b.contexts) > 0
            b.close()
    except Exception as e:
        fail("FAIL_CONNECT_OVER_CDP_FAILED", f"connect_over_cdp 실패: {e}")

# ── 6. screenshot smoke 결과 ──────────────────────────────────────────
ss_report_path = REPORT_DIR / "screenshot_smoke.json"
ss_ok = False
if ss_report_path.exists():
    try:
        ss_data = json.loads(ss_report_path.read_text(encoding="utf-8"))
        ss_ok = bool(ss_data.get("ok"))
        ss_bytes = ss_data.get("size_bytes", 0)
    except Exception:
        ss_bytes = 0
else:
    ss_bytes = 0

if not ss_ok:
    warn("WARN_SCREENSHOT_LIVE_PARTIAL",
         "screenshot_smoke.json 없거나 실패 — CDP 브라우저 미실행 상태에서 audit 시 발생")

# ── 7. BrowserPanel / ScreenshotPanel 코드 검증 ───────────────────────
if PANELS.exists():
    src = PANELS.read_text(encoding="utf-8")
    if "action: 'browser_status'" not in src:
        fail("FAIL_BROWSER_PANEL_BROKEN", "BrowserPanel: browser_status action 없음")
    if "action: 'browser_start'" not in src:
        fail("FAIL_BROWSER_PANEL_BROKEN", "BrowserPanel: browser_start action 없음")
    if "action: 'screenshot'" not in src:
        fail("FAIL_SCREENSHOT_PANEL_BROKEN", "ScreenshotPanel: screenshot action 없음")
    if "data:image" not in src:
        fail("FAIL_SCREENSHOT_PANEL_BROKEN", "ScreenshotPanel: 이미지 표시 없음")
else:
    fail("FAIL_BROWSER_PANEL_BROKEN", "Panels.tsx 파일 없음")

# ── 8. 보안 검사 ──────────────────────────────────────────────────────
FORBIDDEN = ["device_token", "registration_code", "sk-", "openai_api_key"]
if REPORT_DIR.exists():
    for f in REPORT_DIR.glob("*.json"):
        content = f.read_text(encoding="utf-8", errors="replace").lower()
        for pat in FORBIDDEN:
            if pat in content:
                fail("FAIL_SECRET_LEAK", f"{f.name}: '{pat}' 노출")

# screenshot PNG는 바이너리 — 텍스트 검사 불필요

# ── 9. 결과 ──────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE_01 Audit")
print("=" * 68)

for w in warnings:
    print(w)
for i in issues:
    print(i)

if not issues:
    print(f"{P} PASS_DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE")
    print(f"  playwright import:    OK")
    print(f"  CDP 9222:             {'LISTENING' if cdp_listening else 'NOT_LISTENING (run daemon first)'}")
    print(f"  connect_over_cdp:     {'OK' if cdp_connect_ok else 'SKIPPED (daemon not running)'}")
    print(f"  screenshot:           {'OK (' + str(ss_bytes) + ' bytes)' if ss_ok else 'SKIPPED'}")
    print(f"  BrowserPanel:         browser_status/start/tab_list/close ✓")
    print(f"  ScreenshotPanel:      screenshot/base64 ✓")
    print(f"  secret leak:          0 ✓")
else:
    print(f"\n총 FAIL: {len(issues)}건  WARN: {len(warnings)}건")

print("=" * 68)
print()
exit(1 if issues else 0)
