#!/usr/bin/env python3
"""audit_desktop_ui_browser_screenshot_wiring.py
DESKTOP_UI_BROWSER_SCREENSHOT_WIRING_01 감사 스크립트.

Verdicts:
  PASS_DESKTOP_UI_BROWSER_SCREENSHOT_WIRING
  WARN_SCREENSHOT_LIVE_NOT_AVAILABLE
  FAIL_BROWSER_ACTION_MISSING
  FAIL_SCREENSHOT_PANEL_EMPTY
  FAIL_WS_ACTION_NAME_MISMATCH
  FAIL_STORE_HANDLER_MISSING
  FAIL_SECRET_LEAK
  FAIL_AGENT_LINE_TOUCHED
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PANELS = ROOT / "desktop/ui/src/components/panels/Panels.tsx"
STORE  = ROOT / "desktop/ui/src/store/appStore.ts"
WS_TS  = ROOT / "desktop/ui/src/lib/ws.ts"
SERVER = ROOT / "desktop/local_server.py"

PASS_COLOR  = "\033[32m"
WARN_COLOR  = "\033[33m"
FAIL_COLOR  = "\033[31m"
RESET       = "\033[0m"

issues: list[str] = []
warnings: list[str] = []


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def chk(condition: bool, fail_code: str, msg: str) -> None:
    if not condition:
        issues.append(f"{FAIL_COLOR}[FAIL] {fail_code}{RESET} — {msg}")


def warn(condition: bool, warn_code: str, msg: str) -> None:
    if not condition:
        warnings.append(f"{WARN_COLOR}[WARN] {warn_code}{RESET} — {msg}")


panels = _read(PANELS)
store  = _read(STORE)
ws_src = _read(WS_TS)
server = _read(SERVER)

# ── BrowserPanel actions ──────────────────────────────────────────────────────
chk("action: 'browser_status'" in panels,  "FAIL_BROWSER_ACTION_MISSING", "browser_status 미전송")
chk("action: 'browser_start'"  in panels,  "FAIL_BROWSER_ACTION_MISSING", "browser_start 미전송")
chk("action: 'browser_quit'"   in panels,  "FAIL_BROWSER_ACTION_MISSING", "browser_quit 미전송")
chk("action: 'tab_list'"       in panels,  "FAIL_BROWSER_ACTION_MISSING", "tab_list 미전송")
chk("action: 'tab_close'"      in panels,  "FAIL_BROWSER_ACTION_MISSING", "tab_close 미전송")

# ── ScreenshotPanel ───────────────────────────────────────────────────────────
chk("action: 'screenshot'"  in panels,  "FAIL_SCREENSHOT_PANEL_EMPTY", "screenshot action 미전송")
chk("data:image"            in panels or "base64" in panels,
    "FAIL_SCREENSHOT_PANEL_EMPTY", "이미지 표시 경로 없음")

# ── WS type 일치 ─────────────────────────────────────────────────────────────
chk("'tab_list'"          in ws_src, "FAIL_WS_ACTION_NAME_MISMATCH", "WS 타입: tab_list 없음")
chk("'screenshot_result'" in ws_src, "FAIL_WS_ACTION_NAME_MISMATCH", "WS 타입: screenshot_result 없음")
chk("BrowserTab"          in ws_src, "FAIL_WS_ACTION_NAME_MISMATCH", "BrowserTab interface 없음")

# ── store handler ─────────────────────────────────────────────────────────────
chk("browserTabsState"      in store, "FAIL_STORE_HANDLER_MISSING", "browserTabsState 없음")
chk("screenshotState"       in store, "FAIL_STORE_HANDLER_MISSING", "screenshotState 없음")
chk("case 'tab_list'"       in store, "FAIL_STORE_HANDLER_MISSING", "tab_list handler 없음")
chk("case 'screenshot_result'" in store, "FAIL_STORE_HANDLER_MISSING", "screenshot_result handler 없음")

# ── backend action ────────────────────────────────────────────────────────────
chk('action == "screenshot"' in server, "FAIL_BROWSER_ACTION_MISSING", "server: screenshot 핸들러 없음")
chk("screenshot_result"      in server, "FAIL_BROWSER_ACTION_MISSING", "server: screenshot_result 응답 없음")

# ── secret leak (BrowserPanel/ScreenshotPanel 구간만 검사) ───────────────────
browser_section = ""
if "export function BrowserPanel" in panels:
    start = panels.index("export function BrowserPanel")
    # 다음 export function 까지 추출
    next_export = panels.find("export function", start + 10)
    browser_section = panels[start: next_export if next_export > 0 else start + 8000]
for kw in ["device_token", "password"]:
    chk(kw.lower() not in browser_section.lower(), "FAIL_SECRET_LEAK",
        f"BrowserPanel/ScreenshotPanel 구간에 '{kw}' 노출")

# ── agent line ────────────────────────────────────────────────────────────────
chk("local_agent.gui_" not in panels, "FAIL_AGENT_LINE_TOUCHED", "gui_* import 감지")

# ── warn: live stream ─────────────────────────────────────────────────────────
warn(False, "WARN_SCREENSHOT_LIVE_NOT_AVAILABLE",
     "스크린샷은 폴링 방식 (요청 시 1회 캡처). 실시간 스트리밍 미구현 — 필요 시 별도 공정 필요")

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print("  DESKTOP_UI_BROWSER_SCREENSHOT_WIRING_01 Audit")
print("=" * 64)

for w in warnings:
    print(w)
for i in issues:
    print(i)

if not issues:
    print(f"{PASS_COLOR}[PASS] PASS_DESKTOP_UI_BROWSER_SCREENSHOT_WIRING{RESET}")
    print(f"  BrowserPanel:    browser_status / start / quit / tab_list / tab_close ✓")
    print(f"  ScreenshotPanel: screenshot action / base64 표시 ✓")
    print(f"  WS types:        tab_list / screenshot_result / BrowserTab ✓")
    print(f"  Store handlers:  browserTabsState / screenshotState ✓")
    print(f"  Secret leak:     0 ✓")
    print(f"  Agent line:      미수정 ✓")
else:
    print(f"\n총 FAIL: {len(issues)}건")

print("=" * 64 + "\n")
exit(1 if issues else 0)
