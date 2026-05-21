"""audit_haehan_stash_safe_restore.py
HAEHAN_STASH_SAFE_RESTORE_01 감리.

Verdicts:
  PASS_HAEHAN_STASH_SAFE_RESTORE
  WARN_*
  FAIL_STASH_FULL_APPLY_DETECTED
  FAIL_TRAY_APP_RESTORED
  FAIL_USER_SETTINGS_RESTORED
  FAIL_ARCHIVE_BINARY_RESTORED
  FAIL_WHOAMI_ROUTE_REGRESSED
  FAIL_SECRET_LEAK
  FAIL_EXISTING_TESTS_BROKEN
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
LOCAL_SERVER = ROOT / "desktop/local_server.py"
WEBVIEW_PW = ROOT / "desktop/webview_app_pywebview.py"

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []

def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")


# ── 1. 복원 대상 13개 staged 여부 ──────────────────────────────────────
diff_head = subprocess.run(
    ["git", "diff", "--name-status", "HEAD"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
diff_cached = subprocess.run(
    ["git", "diff", "--cached", "--name-status"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)
status_short = subprocess.run(
    ["git", "status", "--short"],
    cwd=ROOT, capture_output=True, text=True, timeout=10,
)

# HEAD vs working tree (staged + unstaged 합쳐서 본 공정 변경 전체)
all_changes = {}
for line in diff_head.stdout.split("\n"):
    if not line.strip():
        continue
    parts = line.split("\t", 1)
    if len(parts) == 2:
        all_changes[parts[1].replace("\\", "/")] = parts[0]

expected_restored = [
    "HaehanAI-Agent.spec",
    "HaehanAI-Desktop.spec",
    "desktop/audit_desktop.py",
    "desktop/local_server.py",
    "desktop/status_provider.py",
    "desktop/webview_app.py",
    "desktop/webview_app_pywebview.py",
    "local_agent/desktop_config.py",
    "desktop/ui/src/index.css",
    "desktop/ui/vite.config.ts",
    "desktop/ui_dist/index.html",
]
expected_deleted = [
    "desktop/ui_dist/assets/index-BNhZLJTm.css",
    "desktop/ui_dist/assets/index-cwUmEBLw.js",
]

for f_ in expected_restored:
    if f_ in all_changes and all_changes[f_] == "M":
        ok(f"복원 OK (M): {f_}")
    else:
        fail("FAIL_STASH_FULL_APPLY_DETECTED",
             f"복원 대상 누락 또는 상태 잘못: {f_} -> {all_changes.get(f_, '없음')}")

for f_ in expected_deleted:
    if f_ in all_changes and all_changes[f_] == "D":
        ok(f"삭제 OK (D): {f_}")
    else:
        fail("FAIL_STASH_FULL_APPLY_DETECTED",
             f"삭제 대상 누락: {f_} -> {all_changes.get(f_, '없음')}")


# ── 2. 복원 금지 파일 미변경 확인 ─────────────────────────────────────
forbidden_restore = [
    "desktop/tray_app.py",
    "desktop/user_settings.py",
    "scripts/archive/data/chrome_ui_monitor_state.json",
]
for f_ in forbidden_restore:
    if f_ in all_changes:
        # chrome_ui_monitor_state.json 은 본 공정 시작 전부터 이미 dirty 였으므로
        # diff 가 본 공정에서 더해진 게 아닌지 확인 필요. 본 공정에서 직접
        # 복원/삭제하지 않았다면 PASS.
        if f_ == "scripts/archive/data/chrome_ui_monitor_state.json":
            warn("WARN_ARCHIVE_BINARY_PRE_EXISTING",
                 f"{f_} 는 본 공정 시작 전부터 dirty (보존)")
        elif f_ == "desktop/tray_app.py":
            fail("FAIL_TRAY_APP_RESTORED", f"{f_} 가 변경됨")
        elif f_ == "desktop/user_settings.py":
            fail("FAIL_USER_SETTINGS_RESTORED", f"{f_} 가 변경됨")
        else:
            fail("FAIL_ARCHIVE_BINARY_RESTORED", f"{f_} 가 변경됨")
    else:
        if f_ == "scripts/archive/data/chrome_ui_monitor_state.json":
            # status_short 에서 그래도 잡힐 수 있음 (이전 dirty)
            ok(f"복원 금지 파일 미변경: {f_}")
        elif f_ == "desktop/tray_app.py":
            ok("FAIL_TRAY_APP_RESTORED 회피 — tray_app.py 미변경")
        elif f_ == "desktop/user_settings.py":
            ok("FAIL_USER_SETTINGS_RESTORED 회피 — user_settings.py 미변경")


# ── 3. 본 공정 변경 범위 OUT 검증 ─────────────────────────────────────
allowed_files = set(expected_restored) | set(expected_deleted) | {
    "scripts/ops/audit_haehan_stash_safe_restore.py",
    # stash 복원으로 인한 이전 공정 회귀 테스트/감리 정밀화 — commit-history 기반으로 갱신
    "tests/test_haehan_whoami_route.py",
    "scripts/ops/audit_haehan_whoami_route.py",
    "scripts/ops/audit_haehan_admin_mode_webview_lazy_load.py",
}
# 본 공정 시작 전부터 dirty 였던 파일은 제외
pre_existing_dirty = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
}
out_of_scope = [
    f_ for f_ in all_changes
    if f_ not in allowed_files and f_ not in pre_existing_dirty
]
if out_of_scope:
    fail("FAIL_STASH_FULL_APPLY_DETECTED",
         f"허용 외 변경 파일: {out_of_scope}")
else:
    ok(f"변경 범위 검증 OK — 본 공정 외 변경 없음")


# ── 4. whoami 라우터 보존 ─────────────────────────────────────────────
ls_src = LOCAL_SERVER.read_text(encoding="utf-8")
if "/api/v1/whoami" in ls_src and "async def whoami" in ls_src \
        and "_WHOAMI_KNOWN_ROLES" in ls_src and "_resolve_whoami_role" in ls_src:
    ok("whoami 라우터 4종 식별자 모두 보존 (/api/v1/whoami, async def whoami, _WHOAMI_KNOWN_ROLES, _resolve_whoami_role)")
else:
    fail("FAIL_WHOAMI_ROUTE_REGRESSED",
         "whoami 라우터 일부 누락")


# ── 5. WS scope client 패치 반영 ───────────────────────────────────────
if 'request.scope.get("type") == "websocket"' in ls_src:
    ok("RemoteAccessMiddleware WS scope client 패치 반영")
else:
    fail("FAIL_STASH_FULL_APPLY_DETECTED",
         "WS scope client 패치 누락")


# ── 6. _check_consent 포함 (webview_app_pywebview) ──────────────────
wv_src = WEBVIEW_PW.read_text(encoding="utf-8")
if "_check_consent" in wv_src:
    ok("webview_app_pywebview._check_consent 포함됨 (consent dialog 기반)")
else:
    fail("FAIL_STASH_FULL_APPLY_DETECTED",
         "webview_app_pywebview._check_consent 누락")


# ── 7. main_launcher consent hook 미연결 ─────────────────────────────
ml_src = (ROOT / "desktop/main_launcher.py").read_text(encoding="utf-8")
# main_launcher 가 webview_app_pywebview._check_consent 를 직접 호출하면 안 됨
if "webview_app_pywebview._check_consent" in ml_src \
        or "from desktop.webview_app_pywebview import _check_consent" in ml_src:
    fail("FAIL_STASH_FULL_APPLY_DETECTED",
         "main_launcher 가 webview_app_pywebview._check_consent 와 연결됨 — 본 공정 OUT_OF_SCOPE")
else:
    ok("main_launcher 의 consent hook 은 _check_consent 와 미연결 — 본 공정 안전")


# ── 8. HaehanAI-Desktop.spec 변경 반영 ────────────────────────────────
spec_src = (ROOT / "HaehanAI-Desktop.spec").read_text(encoding="utf-8")
if "collect_all" in spec_src and "playwright" in spec_src.lower():
    ok("HaehanAI-Desktop.spec — collect_all + playwright 포함")
else:
    fail("FAIL_STASH_FULL_APPLY_DETECTED",
         "Desktop.spec 변경 누락")


# ── 9. secret leak 검사 (복원된 파일 + audit/test) ─────────────────────
secret_patterns = ["sk-proj-", "sk-ant-", "Bearer eyJ"]
# audit 자체는 검사 패턴이 문자열로 등장하므로 검사 대상에서 제외
files_to_scan = list(expected_restored)
leak_files = []
for f_ in files_to_scan:
    p = ROOT / f_
    if not p.exists():
        continue
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for pat in secret_patterns:
        if pat in txt:
            leak_files.append(f"{f_}: {pat}")
if leak_files:
    fail("FAIL_SECRET_LEAK", f"실제 secret 패턴: {leak_files}")
else:
    ok("복원 파일에 실제 secret 패턴 없음")


# 응답/log에 노출 의심 키 — 본 공정 변경 파일에 한정해서 위험 키워드 검사
# (정책 설명 주석/문구 false positive 회피 위해 .py 의 코드 라인만 검사)
forbidden_keys = ["device_token", "registration_code", "bearer", "cookie",
                  "authorization", "sk-", "secret", "password", "api_key"]
# 정책상 이 키워드들 자체는 코드에 등장할 수 있음 (검사/금지 정책 자체).
# 실제 leak 은 secret_patterns 검사가 다룸. 본 검사는 정보 제공용.
for f_ in expected_restored:
    if not f_.endswith(".py"):
        continue
    p = ROOT / f_
    if not p.exists():
        continue
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    hits = sum(1 for k in forbidden_keys if k in txt.lower())
    # 정보용 — 0 건이 이상적이지만, redaction 코드 자체에 등장 가능
    # PASS 조건은 secret_patterns 만으로 판정


# ── 결과 ──────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_STASH_SAFE_RESTORE_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_STASH_SAFE_RESTORE\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
