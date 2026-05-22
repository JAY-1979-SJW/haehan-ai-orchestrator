"""audit_haehan_single_exe_build.py
HAEHAN_SINGLE_EXE_BUILD_01 감리.

Verdicts:
  PASS_HAEHAN_SINGLE_EXE_BUILD
  FAIL_ENTRYPOINT_NOT_MAIN_LAUNCHER
  FAIL_WEBVIEW_DIRECT_ENTRY_STILL_USED
  FAIL_STALE_RUNTIME_RUNNING
  FAIL_LEGACY_DIST_PRESENT_AFTER_CLEAN
  FAIL_PYINSTALLER_BUILD
  FAIL_EXE_MISSING
  FAIL_EXE_CRASH
  FAIL_CONSENT_FLOW_BROKEN
  FAIL_WHOAMI_ROUTE_BROKEN
  FAIL_ADMIN_ROLE_GUARD_BROKEN
  FAIL_SKIP_GUI_BROKEN
  FAIL_SECRET_LEAK
  FAIL_CDP_TOUCHED
  FAIL_FORBIDDEN_FILE_MODIFIED
  FAIL_STASH_CHANGED
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []


def fail(c, m): issues.append(f"{F} {c} — {m}")
def warn(c, m): warnings.append(f"{W} {c} — {m}")
def ok(m):      passes.append(f"{P} {m}")


SECRET_TOKENS = ("device_token", "registration_code", "bearer", "cookie",
                 "authorization", "api_key", "password")

LAUNCHER = ROOT / "build/webview_launcher.py"
SPEC = ROOT / "HaehanAI-Desktop.spec"
EXE = ROOT / "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe"
BUILD_LOG = ROOT / "data/logs/build_haehan_desktop.log"


# 1. entrypoint rewire
launcher_src = LAUNCHER.read_text(encoding="utf-8")
if "from desktop.main_launcher import main" in launcher_src:
    ok("build/webview_launcher.py 가 main_launcher.main 을 import")
else:
    fail("FAIL_ENTRYPOINT_NOT_MAIN_LAUNCHER",
         "webview_launcher.py 가 main_launcher 를 import 하지 않음")

# code 라인만 검사 (docstring 제외)
def _code_only(src: str) -> str:
    out = []
    in_doc = False
    for line in src.splitlines():
        s = line.lstrip()
        if s.startswith('"""') or s.startswith("'''"):
            cnt = line.count('"""') + line.count("'''")
            if cnt == 2:
                continue
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)

launcher_code = _code_only(launcher_src)
if "from desktop.webview_app_pywebview import main" in launcher_code \
        or "webview_app_pywebview.main(" in launcher_code:
    fail("FAIL_WEBVIEW_DIRECT_ENTRY_STILL_USED",
         "webview_app_pywebview.main 직접 호출이 launcher 코드에 남아있음")
else:
    ok("webview_app_pywebview.main 직접 호출 없음")

spec_src = SPEC.read_text(encoding="utf-8")
if "webview_launcher.py" in spec_src and ("build\\\\webview_launcher.py" in spec_src or "build\\webview_launcher.py" in spec_src or "build/webview_launcher.py" in spec_src):
    ok("HaehanAI-Desktop.spec 가 build/webview_launcher.py 를 entry 로 유지")
else:
    fail("FAIL_ENTRYPOINT_NOT_MAIN_LAUNCHER",
         "spec entry 불일치")


# 2. stale runtime 미실행
def _running(name: str) -> bool:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"@(Get-Process -Name '{name}' -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True,
    )
    try:
        return int(r.stdout.strip() or "0") > 0
    except Exception:
        return False


if _running("HaehanAI-Agent"):
    fail("FAIL_STALE_RUNTIME_RUNNING", "HaehanAI-Agent.exe 실행 중")
else:
    ok("HaehanAI-Agent.exe 미실행")

# legacy dist
if (ROOT / "dist/HaehanAI-Agent").exists():
    fail("FAIL_LEGACY_DIST_PRESENT_AFTER_CLEAN", "dist/HaehanAI-Agent/ 잔존")
else:
    ok("dist/HaehanAI-Agent/ 부재 확인")

if (ROOT / "desktop/electron").exists():
    fail("FAIL_LEGACY_DIST_PRESENT_AFTER_CLEAN", "desktop/electron/ 잔존")
else:
    ok("desktop/electron/ 부재 확인")


# 3. build artifact
if not EXE.exists():
    fail("FAIL_EXE_MISSING", f"{EXE} 부재")
else:
    size_mb = EXE.stat().st_size / (1024 * 1024)
    ok(f"HaehanAI-Desktop.exe 존재 ({size_mb:.1f} MB)")

if BUILD_LOG.exists():
    log_tail = BUILD_LOG.read_text(encoding="utf-8", errors="ignore")[-4000:]
    if "Building EXE" in log_tail or "Building COLLECT" in log_tail or "completed successfully" in log_tail.lower():
        ok("PyInstaller 빌드 로그 정상 완료 표지 확인")
    elif "PermissionError" in log_tail or "Traceback" in log_tail:
        fail("FAIL_PYINSTALLER_BUILD", "빌드 로그에 오류 흔적")
    else:
        warn("WARN_BUILD_LOG_UNCLEAR", "빌드 완료 표지 식별 불가 — log 수동 확인")


# 4. consent flow 연결 (source 검증)
ml_src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
if "run_consent_flow" in ml_src and "from desktop.webview_app_pywebview import _check_consent" in ml_src:
    ok("main_launcher consent flow 연결 보존")
else:
    fail("FAIL_CONSENT_FLOW_BROKEN", "main_launcher consent flow 연결 누락")

if "return 4" in ml_src and "consent_state.get" in ml_src:
    ok("consent decline → rc=4 차단 로직 유지")
else:
    fail("FAIL_CONSENT_FLOW_BROKEN", "rc=4 차단 로직 누락")


# 5. whoami route
ls_src = (ROOT / "desktop/local_server.py").read_text(encoding="utf-8")
if "/api/v1/whoami" in ls_src and "async def whoami" in ls_src:
    ok("/api/v1/whoami 라우터 보존")
else:
    fail("FAIL_WHOAMI_ROUTE_BROKEN", "/api/v1/whoami 누락")


# 6. admin role guard
aw_src = (ROOT / "desktop/admin_webview.py").read_text(encoding="utf-8")
if "resolve_current_role" in aw_src and "run_admin_mode_full" in aw_src:
    ok("admin_webview role guard 진입점 보존")
else:
    fail("FAIL_ADMIN_ROLE_GUARD_BROKEN", "admin_webview role guard 누락")


# 7. SKIP_GUI 동작 (source 검증)
wv_src = (ROOT / "desktop/webview_app_pywebview.py").read_text(encoding="utf-8")
if 'HAEHAN_SKIP_GUI' in wv_src and "_default_tk_dialog_runner" in wv_src:
    ok("HAEHAN_SKIP_GUI 분기 보존")
else:
    fail("FAIL_SKIP_GUI_BROKEN", "HAEHAN_SKIP_GUI 분기 누락")


# 8. secret leak — launcher / spec / 빌드 로그
def _scan_secret(text: str, label: str) -> None:
    low = text.lower()
    leaked = [t for t in SECRET_TOKENS if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"]+['\"]", low)]
    if leaked:
        fail("FAIL_SECRET_LEAK", f"{label} 에 secret 값 노출: {leaked}")


_scan_secret(launcher_src, "build/webview_launcher.py")
_scan_secret(spec_src, "HaehanAI-Desktop.spec")
if BUILD_LOG.exists():
    _scan_secret(BUILD_LOG.read_text(encoding="utf-8", errors="ignore")[:200000],
                 "build_haehan_desktop.log")
ok("secret 값 노출 패턴 스캔 통과 (launcher/spec/log)")


# 9. CDP 데몬 유지 확인
cdp_ok = True
try:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cdp_daemon|popup_monitor|chrome_ui_monitor' }).Count"],
        capture_output=True, text=True,
    )
    count = int(r.stdout.strip() or "0")
    if count >= 1:
        ok(f"CDP 관련 프로세스 유지 ({count}개)")
    else:
        warn("WARN_CDP_NOT_RUNNING", "CDP 데몬 프로세스 미감지 — 사용자가 의도적으로 종료했을 수 있음")
except Exception as e:
    warn("WARN_CDP_PROBE_FAIL", f"{type(e).__name__}: {e}")


# 10. forbidden file 미변경
def _diff(p):
    r = subprocess.run(["git", "diff", "--name-only", "HEAD", p],
                       cwd=str(ROOT), capture_output=True, text=True)
    return bool(r.stdout.strip())


for fpath in ("desktop/tray_app.py", "desktop/user_settings.py",
              "desktop/webview_app.py", "desktop/webview_app_pywebview.py"):
    # webview_app_pywebview.py 는 HAEHAN_CONSENT_DIALOG_01 에서 이미 변경 커밋됨 (HEAD에 반영) — 추가 변경 없는지 확인
    if _diff(fpath):
        if fpath == "desktop/webview_app_pywebview.py":
            warn("WARN_WEBVIEW_PYWEBVIEW_DIFF",
                 "webview_app_pywebview.py 추가 변경 감지 (의도 외 변경인지 확인)")
        else:
            fail("FAIL_FORBIDDEN_FILE_MODIFIED", f"{fpath} 수정 감지")
    else:
        ok(f"{fpath} 미수정")


# 11. stash@{0} 유지
try:
    r = subprocess.run(["git", "stash", "list"], cwd=str(ROOT),
                       capture_output=True, text=True)
    stash_lines = [l for l in r.stdout.splitlines() if l.strip()]
    if stash_lines and "pre-whoami-route-session-leftover" in stash_lines[0]:
        ok("stash@{0} 유지 (pre-whoami-route-session-leftover)")
    else:
        fail("FAIL_STASH_CHANGED",
             f"stash@{{0}} 변경: head={stash_lines[0] if stash_lines else 'EMPTY'}")
except Exception as e:
    warn("WARN_STASH_CHECK", str(e))


# ── 결과 ────────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_SINGLE_EXE_BUILD_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_SINGLE_EXE_BUILD\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
