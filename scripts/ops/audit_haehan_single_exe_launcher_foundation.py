"""audit_haehan_single_exe_launcher_foundation.py
HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01 감리.

Verdicts:
  PASS_HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION
  WARN_TRAY_MODE_HOOK_ONLY
  WARN_ADMIN_MODE_HOOK_ONLY
  WARN_ROLE_GUARD_DEFERRED
  FAIL_LAUNCHER_MISSING
  FAIL_MODE_BRANCHING_MISSING
  FAIL_LOCK_POLICY_MISSING
  FAIL_SECRET_LEAK
  FAIL_EXISTING_ENTRYPOINT_BROKEN
"""
from __future__ import annotations
import importlib
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
LAUNCHER = ROOT / "desktop/main_launcher.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues = []
warnings = []
passes = []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")


# ── 1. launcher 모듈 존재 ────────────────────────────────────────────────
if not LAUNCHER.exists():
    fail("FAIL_LAUNCHER_MISSING", f"launcher 파일 없음: {LAUNCHER}")
else:
    ok(f"launcher 존재 ({LAUNCHER.stat().st_size:,} bytes)")


# ── 2. import 가능성 ─────────────────────────────────────────────────────
sys.path.insert(0, str(ROOT))
try:
    from desktop import main_launcher as ml
    ok(f"import OK — version={ml.__version__}")
except Exception as e:
    fail("FAIL_LAUNCHER_MISSING", f"import 실패: {e}")
    print(*issues, sep="\n")
    sys.exit(1)


# ── 3. CLI mode 분기 ─────────────────────────────────────────────────────
required_modes = ["TRAY", "ADMIN", "DIAGNOSTICS", "VERSION", "RESET_LOCK"]
missing = [m for m in required_modes if not hasattr(ml.AppMode, m)]
if missing:
    fail("FAIL_MODE_BRANCHING_MISSING", f"AppMode 누락: {missing}")
else:
    ok(f"AppMode 정의 ({len(required_modes)}개): {required_modes}")

# parse_mode 동작 확인
test_cases = [
    ([], ml.AppMode.TRAY),
    (["--tray"], ml.AppMode.TRAY),
    (["--admin"], ml.AppMode.ADMIN),
    (["--diagnostics"], ml.AppMode.DIAGNOSTICS),
    (["--version"], ml.AppMode.VERSION),
    (["--reset-lock"], ml.AppMode.RESET_LOCK),
]
all_branch_ok = True
for argv, expected in test_cases:
    try:
        got = ml.parse_mode(argv)
        if got == expected:
            ok(f"parse_mode({argv}) → {expected.value}")
        else:
            fail("FAIL_MODE_BRANCHING_MISSING", f"parse_mode({argv}) → {got} != {expected}")
            all_branch_ok = False
    except SystemExit:
        fail("FAIL_MODE_BRANCHING_MISSING", f"parse_mode({argv}) 인자 거절")
        all_branch_ok = False


# ── 4. 단일 인스턴스 락 ──────────────────────────────────────────────────
required_fns = ["acquire_lock", "release_lock", "reset_lock", "lock_path", "_pid_alive"]
missing_fns = [f for f in required_fns if not hasattr(ml, f)]
if missing_fns:
    fail("FAIL_LOCK_POLICY_MISSING", f"락 함수 누락: {missing_fns}")
else:
    ok(f"락 함수 정의: {required_fns}")

# lock_path 위치 확인
lp = ml.lock_path()
if "HaehanAI" in str(lp):
    ok(f"lock_path → {lp.parent}")
else:
    warn("WARN_LOCK_PATH", f"lock_path 의심: {lp}")

# stale lock 처리
import os, json
fake_pid = 9999999  # 거의 확실히 죽은 PID
lp.parent.mkdir(parents=True, exist_ok=True)
lp.write_text(json.dumps({"pid": fake_pid}), encoding="utf-8")
state = ml.acquire_lock()
if state.acquired and state.stale:
    ok("stale lock 자동 정리 동작")
    ml.release_lock()
else:
    warn("WARN_STALE_LOCK", f"stale 처리 결과: {state}")

# reset_lock 동작
lp.write_text(json.dumps({"pid": fake_pid}), encoding="utf-8")
r = ml.reset_lock()
if r.get("ok"):
    ok("reset_lock OK")
else:
    fail("FAIL_LOCK_POLICY_MISSING", f"reset_lock 실패: {r}")


# ── 5. lifecycle hooks ──────────────────────────────────────────────────
required_hooks = [
    "check_consent_hook", "load_token_status_hook", "role_check_hook",
    "start_local_server_hook", "start_tray_hook",
    "start_admin_webview_hook", "graceful_shutdown_hook",
]
missing_hooks = [h for h in required_hooks if not hasattr(ml, h)]
if missing_hooks:
    fail("FAIL_LAUNCHER_MISSING", f"lifecycle hook 누락: {missing_hooks}")
else:
    ok(f"lifecycle hook 정의 ({len(required_hooks)}개)")

# hook은 deferred 상태여야 함 (실제 구현은 후속)
if hasattr(ml, "start_tray_hook"):
    r = ml.start_tray_hook()
    if r.get("deferred"):
        warn("WARN_TRAY_MODE_HOOK_ONLY", "Tray 실제 구현은 HAEHAN_TRAY_REGISTRATION_MERGE_01 에서")
if hasattr(ml, "start_admin_webview_hook"):
    r = ml.start_admin_webview_hook()
    if r.get("deferred"):
        warn("WARN_ADMIN_MODE_HOOK_ONLY", "Admin webview 실제 구현은 HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서")
if hasattr(ml, "role_check_hook"):
    r = ml.role_check_hook(ml.AppMode.ADMIN)
    if r.get("deferred"):
        warn("WARN_ROLE_GUARD_DEFERRED", "role guard 실제 구현은 HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서")


# ── 6. diagnostics 출력 redaction ───────────────────────────────────────
buf = io.StringIO()
with redirect_stdout(buf):
    ml.print_diagnostics(ml.AppMode.DIAGNOSTICS)
output = buf.getvalue()

# 금지 패턴 (실제 secret 값) 없어야 함
forbidden_patterns = [
    "sk-proj-", "sk-ant-", "Bearer eyJ",
]
leaks = [p for p in forbidden_patterns if p in output]
if leaks:
    fail("FAIL_SECRET_LEAK", f"diagnostics 출력에 secret 의심: {leaks}")
else:
    ok("diagnostics 출력 secret 없음")

# device_token / registration_code 키 자체가 노출되더라도 값은 안 됨
import re
suspicious = re.findall(r"device_token['\"]?\s*:\s*['\"]([^'\"\[]+)['\"]", output)
suspicious = [s for s in suspicious if s and s != "[REDACTED]"]
if suspicious:
    fail("FAIL_SECRET_LEAK", f"device_token 값 노출: {len(suspicious)}건")
else:
    ok("device_token 원문 없음")


# ── 7. 기존 entrypoint 회귀 ─────────────────────────────────────────────
existing_entries = [
    "desktop.webview_app_pywebview",
    "local_agent.desktop_launcher",
]
broken = []
for mod_name in existing_entries:
    try:
        importlib.import_module(mod_name)
        ok(f"기존 entrypoint OK: {mod_name}")
    except Exception as e:
        broken.append(f"{mod_name}: {e}")

if broken:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN", f"기존 entrypoint 깨짐: {broken}")


# ── 8. main() 직접 호출 — version / reset-lock ────────────────────────────
try:
    rc = ml.main(["--version"])
    if rc == 0:
        ok("main(--version) → 0")
    else:
        warn("WARN_MAIN_RC", f"main(--version) → {rc}")
except SystemExit as e:
    if e.code == 0:
        ok("main(--version) → SystemExit(0)")


# ── 9. secret 누출 검사 — 소스 코드 자체 ────────────────────────────────
src = LAUNCHER.read_text(encoding="utf-8")
src_leaks = []
for pat in ["sk-proj-", "sk-ant-"]:
    if pat in src:
        src_leaks.append(pat)
if src_leaks:
    fail("FAIL_SECRET_LEAK", f"launcher 소스에 secret: {src_leaks}")
else:
    ok("launcher 소스 secret 없음")


# ── 10. local-only bypass 금지 명시 ──────────────────────────────────────
if "local-only bypass 금지" in src or "127.0.0.1 이어도" in src or "local-only" in src.lower():
    ok("local-only bypass 금지 정책 명시")
else:
    warn("WARN_LOCAL_BYPASS_POLICY", "local-only bypass 금지 정책 주석 권장")


# ── 결과 ────────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
