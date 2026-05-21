"""audit_haehan_admin_mode_webview_lazy_load.py
HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 감리.

Verdicts:
  PASS_HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD
  WARN_CONSENT_DIALOG_DEFERRED
  WARN_WHOAMI_API_DEFERRED
  FAIL_ROLE_GUARD_BYPASSED
  FAIL_PYWEBVIEW_NOT_LAZY
  FAIL_SKIP_GUI_BROKEN
  FAIL_SECRET_LEAK
  FAIL_EXISTING_ENTRYPOINT_BROKEN
  FAIL_LOCAL_ONLY_BYPASS
  FAIL_SERVER_KILLED_ON_WINDOW_CLOSE
  FAIL_DIRTY_SCOPE_VIOLATION
"""
from __future__ import annotations
import ast
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

ADMIN_MOD  = ROOT / "desktop/admin_webview.py"
LAUNCHER   = ROOT / "desktop/main_launcher.py"
TRAY_RT    = ROOT / "desktop/tray_runtime.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")


# ── 1. admin_webview 모듈 존재 ───────────────────────────────────────────
if not ADMIN_MOD.exists():
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"admin_webview 없음: {ADMIN_MOD}")
    print(*issues, sep="\n")
    sys.exit(1)
ok(f"admin_webview 존재 ({ADMIN_MOD.stat().st_size:,} bytes)")


# ── 2. pywebview lazy import 검증 (AST) ──────────────────────────────────
src = ADMIN_MOD.read_text(encoding="utf-8")
tree = ast.parse(src)

# top-level imports
top_imports = []
for node in tree.body:
    if isinstance(node, ast.Import):
        for n in node.names:
            top_imports.append(n.name)
    elif isinstance(node, ast.ImportFrom):
        top_imports.append(node.module or "")

webview_at_top = [m for m in top_imports if m and (m == "webview" or m.startswith("webview."))]
if webview_at_top:
    fail("FAIL_PYWEBVIEW_NOT_LAZY",
         f"webview 가 top-level 에 import 됨: {webview_at_top}")
else:
    ok("admin_webview top-level 에 webview import 없음")

# 함수 내부의 webview import 만 허용 확인 — 'import webview' 가 들여쓰기된 라인에서만 등장
has_function_import = False
top_webview_textual = False
for line in src.split("\n"):
    stripped = line.lstrip()
    if stripped.startswith("import webview"):
        if line != stripped:  # 들여쓰기 있음 = 함수 내부
            has_function_import = True
        else:
            top_webview_textual = True
    elif stripped.startswith("from webview"):
        if line != stripped:
            has_function_import = True
        else:
            top_webview_textual = True

if top_webview_textual:
    fail("FAIL_PYWEBVIEW_NOT_LAZY", "들여쓰기 없는 import webview 발견")
if has_function_import:
    ok("admin_webview 내부 함수에서만 webview lazy import")
else:
    warn("WARN_NO_WEBVIEW_IMPORT", "admin_webview 에 webview import 자체가 없음")


# ── 3. import 모듈 ──────────────────────────────────────────────────────
# sys.modules 에서 webview 제거 후 admin_webview 만 import — webview 가 추가되지 않아야 함
for mod_name in list(sys.modules.keys()):
    if mod_name == "webview" or mod_name.startswith("webview."):
        del sys.modules[mod_name]

# admin_webview 도 캐시 제거
for mod_name in list(sys.modules.keys()):
    if mod_name == "desktop.admin_webview":
        del sys.modules[mod_name]

import desktop.admin_webview as aw  # noqa: E402

webview_after_load = [m for m in sys.modules.keys()
                     if m == "webview" or m.startswith("webview.")]
if webview_after_load:
    fail("FAIL_PYWEBVIEW_NOT_LAZY",
         f"admin_webview import 후 webview 가 sys.modules 에 등장: {webview_after_load}")
else:
    ok("admin_webview import 후 webview 미로드 (실제 lazy 확인)")


# ── 4. 필수 심볼 ────────────────────────────────────────────────────────
needed = ["is_admin_role", "RoleGuardResult", "check_role_via_api",
          "resolve_current_role", "open_admin_window", "run_admin_mode_full",
          "is_admin_window_active", "ADMIN_ROLES"]
missing = [s for s in needed if not hasattr(aw, s)]
if missing:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"심볼 누락: {missing}")
else:
    ok(f"필수 심볼 {len(needed)}개 존재")


# ── 5. role guard 통과/차단 ─────────────────────────────────────────────
cases = [
    ("admin", True), ("owner", True), ("ADMIN", True),
    ("any", False), ("user", False), ("viewer", False),
    ("", False), ("guest", False),
]
all_ok = True
for role, expected in cases:
    got = aw.is_admin_role(role)
    if got == expected:
        ok(f"is_admin_role({role!r}) → {got}")
    else:
        fail("FAIL_ROLE_GUARD_BYPASSED",
             f"is_admin_role({role!r}) → {got}, expected {expected}")
        all_ok = False


# ── 6. local-only bypass 금지 ────────────────────────────────────────────
# check_role_via_api 는 server_url 이 127.0.0.1 이라도 role 검사 통과해야만 passed=True
def _fake_api_any(server_url, timeout):
    return {"role": "any", "status": "ok"}

guard = aw.check_role_via_api(
    server_url="http://127.0.0.1:8765",
    api_caller=_fake_api_any,
)
if guard.passed:
    fail("FAIL_LOCAL_ONLY_BYPASS",
         "127.0.0.1 인데 role=any 가 admin guard 통과")
else:
    ok("127.0.0.1 + role=any → 차단 (local-only bypass 금지)")


# ── 7. whoami 응답 secret leak 검사 ──────────────────────────────────────
def _fake_api_with_token(server_url, timeout):
    return {"role": "admin", "device_token": "BAD_LEAK_DO_NOT_USE"}

guard_leak = aw.check_role_via_api(api_caller=_fake_api_with_token)
if guard_leak.passed:
    fail("FAIL_SECRET_LEAK",
         f"whoami 응답에 device_token 있는데 admin 통과: {guard_leak}")
else:
    if "secret" in guard_leak.reason or "forbidden" in guard_leak.reason.lower():
        ok("whoami 응답 secret 키 검출 시 거부")
    else:
        warn("WARN_SECRET_DETECTION", f"secret 거부 사유: {guard_leak.reason}")


# ── 8. HAEHAN_SKIP_GUI 검증 ─────────────────────────────────────────────
os.environ["HAEHAN_SKIP_GUI"] = "1"
aw._reset_admin_window_state()
r = aw.open_admin_window(explicit_role="admin")
if r.get("ok") and not r.get("window_opened") and r.get("skip_gui"):
    ok("HAEHAN_SKIP_GUI=1 + role=admin → 창 미기동 + ok=True")
else:
    fail("FAIL_SKIP_GUI_BROKEN", f"skip_gui 동작 잘못: {r}")
del os.environ["HAEHAN_SKIP_GUI"]


# ── 9. role 차단 시 창 미기동 ───────────────────────────────────────────
aw._reset_admin_window_state()
r2 = aw.open_admin_window(explicit_role="any", skip_gui=False)
if not r2.get("ok") and not r2.get("window_opened"):
    ok("role=any → 창 미기동 + ok=False")
else:
    fail("FAIL_ROLE_GUARD_BYPASSED",
         f"role=any 인데 창 진입: {r2}")


# ── 10. single instance ────────────────────────────────────────────────
aw._reset_admin_window_state()
# 강제 활성화 후 두 번째 호출
import threading as _th
with aw._admin_window_lock:
    # 직접 슬롯 점유 시뮬레이션
    pass
aw._try_acquire_window()
r3 = aw.open_admin_window(explicit_role="admin", skip_gui=True)
if r3.get("reason") == "already_open":
    ok("single instance — 두 번째 호출 already_open")
else:
    warn("WARN_SINGLE_INSTANCE", f"single instance 응답: {r3}")
aw._reset_admin_window_state()


# ── 11. main_launcher 연결 ──────────────────────────────────────────────
launcher_src = LAUNCHER.read_text(encoding="utf-8")
if "from desktop import admin_webview" in launcher_src or \
   "admin_webview.run_admin_mode_full" in launcher_src or \
   "admin_webview.open_admin_window" in launcher_src or \
   "admin_webview.resolve_current_role" in launcher_src:
    ok("main_launcher → admin_webview 연결 확인")
else:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN",
         "main_launcher 에 admin_webview 호출 없음")

if "admin_mode_available=True" in launcher_src:
    ok("launcher run_tray_mode 가 admin_mode_available=True 전달")
else:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN",
         "admin_mode_available=True 전달 누락")


# ── 12. run_admin_mode 동작 ────────────────────────────────────────────
import desktop.main_launcher as ml  # noqa: E402
os.environ["HAEHAN_SKIP_GUI"] = "1"

aw._reset_admin_window_state()
rc_ok = ml.run_admin_mode(explicit_role="admin", skip_gui=True)
if rc_ok == 0:
    ok("run_admin_mode(role=admin, skip_gui=True) → 0")
else:
    fail("FAIL_ROLE_GUARD_BYPASSED",
         f"role=admin 인데 rc={rc_ok}")

aw._reset_admin_window_state()
rc_fail = ml.run_admin_mode(explicit_role="any", skip_gui=True)
if rc_fail == 2:
    ok("run_admin_mode(role=any) → 2 (role 거부)")
else:
    fail("FAIL_ROLE_GUARD_BYPASSED",
         f"role=any 인데 rc={rc_fail} (2 기대)")

del os.environ["HAEHAN_SKIP_GUI"]


# ── 13. tray_runtime → admin_webview lazy 연결 ──────────────────────────
tray_src = TRAY_RT.read_text(encoding="utf-8")
# tray_runtime 도 top-level 에 admin_webview import 하면 안 됨 (lazy 보장)
tray_tree = ast.parse(tray_src)
top_in_tray = []
for node in tray_tree.body:
    if isinstance(node, ast.ImportFrom):
        if (node.module or "").startswith("desktop"):
            for n in node.names:
                top_in_tray.append((node.module, n.name))
admin_top = [t for t in top_in_tray if "admin_webview" in (t[0] or "") or "admin_webview" == t[1]]
if admin_top:
    warn("WARN_TRAY_TOP_ADMIN_IMPORT",
         f"tray_runtime top-level 에 admin_webview import: {admin_top}")
else:
    ok("tray_runtime top-level 에 admin_webview import 없음 (lazy 유지)")

if "open_admin_handler" in tray_src:
    ok("tray_runtime.open_admin_handler 존재")
else:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN",
         "tray_runtime.open_admin_handler 누락")


# ── 14. secret leak 검사 — 소스 ─────────────────────────────────────────
for f in [ADMIN_MOD, LAUNCHER, TRAY_RT]:
    s = f.read_text(encoding="utf-8")
    for pat in ["sk-proj-", "sk-ant-", "Bearer eyJ"]:
        if pat in s:
            fail("FAIL_SECRET_LEAK", f"{f.name}: {pat}")
            break
    else:
        ok(f"{f.name} 소스 secret 없음")


# ── 15. 기존 entrypoint 회귀 ────────────────────────────────────────────
existing = [
    "desktop.webview_app_pywebview",
    "desktop.local_server",
    "local_agent.desktop_launcher",
    "local_agent.token_store",
    "local_agent.registration_client",
    "local_agent.connection_diagnostics",
    "desktop.tray_runtime",
    "desktop.main_launcher",
]
for mod in existing:
    try:
        importlib.import_module(mod)
        ok(f"기존 entrypoint OK: {mod}")
    except Exception as e:
        fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"{mod}: {e}")


# ── 16. dirty scope 검증 ────────────────────────────────────────────────
import subprocess
try:
    # HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 자체의 변경 파일이 allowed 범위 내인지.
    # (이후 공정에서 working tree 가 다른 변경을 가지더라도 본 커밋 자체의 scope 만 검증)
    log_scope = subprocess.run(
        ["git", "log", "--all", "-E",
         "--grep=^feat.haehan.: HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01",
         "-1", "--name-only", "--pretty=format:%H"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    scope_lines = [l for l in log_scope.stdout.strip().split("\n") if l.strip()]
    if not scope_lines:
        warn("WARN_COMMIT_NOT_FOUND",
             "ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 미발견 — working tree fallback")
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        modified_in_diff = [p.strip() for p in diff.stdout.split("\n") if p.strip()]
    else:
        modified_in_diff = [l.strip() for l in scope_lines[1:]]

    allowed = {
        "desktop/admin_webview.py",
        "desktop/main_launcher.py",
        "desktop/tray_runtime.py",
        "scripts/ops/audit_haehan_admin_mode_webview_lazy_load.py",
        "tests/test_haehan_admin_mode_webview_lazy_load.py",
    }
    pre_existing_dirty = {
        "scripts/archive/data/chrome_ui_monitor_state.json",
    }
    scope_violations = [
        m for m in modified_in_diff
        if m.replace("\\", "/") not in allowed
        and m.replace("\\", "/") not in pre_existing_dirty
    ]
    if scope_violations:
        fail("FAIL_DIRTY_SCOPE_VIOLATION",
             f"ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 범위 외: {scope_violations}")
    else:
        ok(f"수정 범위 검증 OK — ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 변경 {len(modified_in_diff)}개 모두 허용 범위")
except Exception as e:
    warn("WARN_DIFF_CHECK", f"확인 실패: {e}")


# ── 17. 기존 webview_app_pywebview.py 미수정 (본 세션 변경분 없음) ──────
# 본 세션에서 webview_app_pywebview.py 는 수정 금지였음.
# 이전 세션에서 dirty 상태였으므로 dirty 자체는 허용 — 단 본 공정 commit 직전에
# git add desktop/webview_app_pywebview.py 가 호출되면 안 됨.
try:
    # HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 자체의 변경 파일에 금지 파일이 없는지.
    # (이후 공정에서 stash 복원 등으로 staged 되더라도 본 검증은 commit history 기준)
    log = subprocess.run(
        ["git", "log", "--all", "-E",
         "--grep=^feat.haehan.: HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01",
         "-1", "--name-only", "--pretty=format:%H"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    lines = [l for l in log.stdout.strip().split("\n") if l.strip()]
    if not lines:
        warn("WARN_COMMIT_NOT_FOUND",
             "ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 미발견 — staged fallback")
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        staged_files = set(p.strip().replace("\\", "/") for p in staged.stdout.split("\n") if p.strip())
        forbidden_staged = {"desktop/webview_app_pywebview.py",
                            "desktop/tray_app.py"}
        bad = forbidden_staged & staged_files
        if bad:
            fail("FAIL_DIRTY_SCOPE_VIOLATION",
                 f"수정 금지 파일이 staged: {bad}")
        else:
            ok("webview_app_pywebview / tray_app staged 없음 (fallback)")
    else:
        commit_files = set(l.strip().replace("\\", "/") for l in lines[1:])
        forbidden_in_commit = {"desktop/webview_app_pywebview.py",
                               "desktop/tray_app.py"}
        bad = forbidden_in_commit & commit_files
        if bad:
            fail("FAIL_DIRTY_SCOPE_VIOLATION",
                 f"ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 자체에 금지 파일: {bad}")
        else:
            ok("ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 커밋 자체에 금지 파일 (webview_app_pywebview/tray_app) 없음")
except Exception as e:
    warn("WARN_STAGED_CHECK", f"커밋 검사 실패: {e}")


# ── 18. 후속 공정 deferred 마커 ────────────────────────────────────────
warn("WARN_CONSENT_DIALOG_DEFERRED",
     "consent dialog GUI 는 본 공정 OUT_OF_SCOPE — 별도 후속 공정")
warn("WARN_WHOAMI_API_DEFERRED",
     "/api/v1/whoami 라우터 실 구현은 별도 공정 — explicit_role / env / mock 으로 검증")


# ── 결과 ────────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
