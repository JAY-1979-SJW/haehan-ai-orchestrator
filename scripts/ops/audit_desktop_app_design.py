"""audit_desktop_app_design.py
HaehanAI Desktop 앱 설계서 감리 — 설계 vs 실제 코드/번들 비교 검증.

판정:
  PASS_DESKTOP_APP_DESIGN  — 모든 항목 통과
  WARN_*                   — 경고 (앱 동작은 가능)
  FAIL_*                   — 즉시 수정 필요
"""
from __future__ import annotations
import json, socket, sys, urllib.request, zipfile
from pathlib import Path

ROOT     = Path(__file__).parent.parent.parent
DIST     = ROOT / "dist/HaehanAI-Desktop"
INTERNAL = DIST / "_internal"
SPEC     = ROOT / "HaehanAI-Desktop.spec"
WEBVIEW  = ROOT / "desktop/main_launcher.py"
SERVER   = ROOT / "desktop/local_server.py"
WATCHDOG = ROOT / "scripts/ops/audit_desktop_app_watchdog.py"
LOG_FILE = ROOT / "data/logs/desktop_app.log"
CONSENT  = ROOT / "data/consent.json"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues   = []
warnings = []
passes   = []

def fail(code, msg): issues.append(f"{F} {code}: {msg}")
def warn(code, msg): warnings.append(f"{W} {code}: {msg}")
def ok(msg):         passes.append(f"{P} {msg}")

# ── S1. 번들 모듈 확인 ────────────────────────────────────────────────────
print("\n[S1] 번들 모듈 확인")
if not INTERNAL.exists():
    fail("FAIL_NO_BUILD", "dist/_internal 없음 — 빌드 필요")
else:
    # base_library.zip 내 필수 모듈
    zip_path = INTERNAL / "base_library.zip"
    zip_names = []
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as z:
            zip_names = z.namelist()

    required = {
        "uvicorn":    any("uvicorn" in n for n in zip_names) or (INTERNAL/"uvicorn").exists(),
        "fastapi":    any("fastapi" in n for n in zip_names) or (INTERNAL/"fastapi").exists(),
        "starlette":  any("starlette" in n for n in zip_names) or (INTERNAL/"starlette").exists(),
        "anyio":      any("anyio" in n for n in zip_names) or (INTERNAL/"anyio").exists(),
        "h11":        any("h11" in n for n in zip_names) or (INTERNAL/"h11").exists(),
        "websockets": (INTERNAL/"websockets").exists(),
        "webview":    (INTERNAL/"webview").exists(),
        "playwright": (INTERNAL/"playwright").exists(),
        "desktop":    (INTERNAL/"desktop").exists(),
        "clr_loader": (INTERNAL/"clr_loader").exists(),
        "psutil":     any("psutil" in n for n in zip_names) or len(list(INTERNAL.glob("psutil*"))) > 0,
    }
    for mod, found in required.items():
        if found: ok(f"번들: {mod}")
        else:     fail(f"FAIL_MISSING_{mod.upper()}", f"_internal에 {mod} 없음")

    # playwright driver
    node = INTERNAL / "playwright/driver/node.exe"
    if node.exists(): ok("playwright driver node.exe")
    else: fail("FAIL_PLAYWRIGHT_DRIVER", "playwright/driver/node.exe 없음")

# ── S2. 로그 설정 확인 ────────────────────────────────────────────────────
print("\n[S2] 로그 설정 확인")
if WEBVIEW.exists():
    src = WEBVIEW.read_text(encoding="utf-8")
    if "_setup_logging" in src:     ok("_setup_logging 함수 존재")
    else: fail("FAIL_NO_LOGGING", "main_launcher에 _setup_logging 없음")

    if "sys.executable" in src or "sys.frozen" in src:
        ok("exe 경로 기반 로그 경로 설정")
    else:
        warn("WARN_LOG_PATH", "exe 실행 시 로그 경로가 소스 기준 — exe에선 data/logs 못 찾을 수 있음")

    if "traceback.format_exc" in src: ok("서버 오류 traceback 포함")
    else: warn("WARN_NO_TRACEBACK", "embedded server error에 traceback 없음")
else:
    fail("FAIL_NO_WEBVIEW", "desktop/main_launcher.py 없음")

# ── S3. 서버 코드 확인 ────────────────────────────────────────────────────
print("\n[S3] 서버 코드 확인")
if SERVER.exists():
    src = SERVER.read_text(encoding="utf-8")
    checks = {
        "health 엔드포인트":      "/health" in src,
        "WS /ws/ui 엔드포인트":   "@app.websocket(\"/ws/ui\")" in src or 'websocket("/ws/ui")' in src,
        "browser_status 핸들러":  'action == "browser_status"' in src,
        "screenshot 핸들러":      'action == "screenshot"' in src,
        "tab_list 핸들러":        'action == "tab_list"' in src,
        "WS scope client 수정":   'scope.get("client")' in src,
    }
    for name, found in checks.items():
        if found: ok(f"서버: {name}")
        else:     fail(f"FAIL_SERVER_{name.replace(' ','_').upper()}", f"서버에 {name} 없음")
else:
    fail("FAIL_NO_SERVER", "local_server.py 없음")

# ── S4. WS 실시간 연결 확인 ──────────────────────────────────────────────
print("\n[S4] 서버 실행 상태 확인")
try:
    urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2)
    ok("서버 8765 응답")
    # WS 연결
    import asyncio, websockets as _wss
    async def _ws_check():
        async with _wss.connect("ws://127.0.0.1:8765/ws/ui", open_timeout=4) as ws:
            await ws.send(json.dumps({"action": "browser_status"}))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            return resp
    resp = asyncio.run(_ws_check())
    ok(f"WS /ws/ui 연결 — cdp_alive={resp.get('cdp_alive')} tab_count={resp.get('tab_count')}")
except Exception as e:
    warn("WARN_SERVER_NOT_RUNNING", f"서버 미실행 또는 WS 실패: {e}")

# ── S5. CDP 확인 ──────────────────────────────────────────────────────────
print("\n[S5] CDP 확인")
s = socket.socket(); s.settimeout(1)
if s.connect_ex(("127.0.0.1", 9222)) == 0:
    s.close()
    try:
        r = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
        ver = json.loads(r.read())
        ok(f"CDP 9222 — {ver.get('Browser','?')}")
    except Exception as e:
        warn("WARN_CDP_VERSION", f"CDP 응답 오류: {e}")
else:
    s.close()
    warn("WARN_CDP_OFF", "CDP 9222 미실행 — 앱 기동 후 browser_start로 실행")

# ── S6. 동의 창 확인 ─────────────────────────────────────────────────────
print("\n[S6] 동의 처리 확인")
if WEBVIEW.exists():
    src = WEBVIEW.read_text(encoding="utf-8")
    if "consent" in src.lower():
        ok("동의(consent) 로직 존재")
    else:
        warn("WARN_NO_CONSENT", "main_launcher에 동의 창 없음 — 추가 필요")
if CONSENT.exists():
    ok(f"consent.json 존재: {CONSENT}")
else:
    warn("WARN_NO_CONSENT_FILE", "consent.json 없음 — 최초 실행 미완료 또는 미구현")

# ── S7. 감사 스크립트 확인 ────────────────────────────────────────────────
print("\n[S7] 감사 스크립트 확인")
if WATCHDOG.exists():
    src = WATCHDOG.read_text(encoding="utf-8")
    for fn in ["check_server", "check_cdp", "check_ws", "check_playwright", "run_once"]:
        if fn in src: ok(f"watchdog: {fn}()")
        else: fail(f"FAIL_WATCHDOG_{fn.upper()}", f"watchdog에 {fn} 없음")
else:
    fail("FAIL_NO_WATCHDOG", "audit_desktop_app_watchdog.py 없음")

# ── S8. ui_dist 확인 ─────────────────────────────────────────────────────
print("\n[S8] UI 빌드 확인")
ui_dist = ROOT / "desktop/ui_dist"
if (ui_dist / "index.html").exists():
    js_files = list(ui_dist.glob("assets/*.js"))
    ok(f"ui_dist/index.html 존재, JS: {len(js_files)}개")
else:
    fail("FAIL_NO_UI_DIST", "desktop/ui_dist/index.html 없음 — npm run build 필요")

# ── 최종 결과 ─────────────────────────────────────────────────────────────
print("\n" + "=" * 68)
print("  HaehanAI Desktop 설계서 감리 결과")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for f in issues:   print(f)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_DESKTOP_APP_DESIGN\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
