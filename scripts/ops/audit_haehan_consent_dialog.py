"""audit_haehan_consent_dialog.py
HAEHAN_CONSENT_DIALOG_01 감리.

Verdicts:
  PASS_HAEHAN_CONSENT_DIALOG
  FAIL_CONSENT_DIALOG_NOT_CONNECTED
  FAIL_CONSENT_SECRET_LEAK
  FAIL_SKIP_GUI_BROKEN
  FAIL_DECLINE_DOES_NOT_BLOCK
  FAIL_CONSENT_FILE_SCHEMA_UNSAFE
  FAIL_EXISTING_ENTRYPOINT_BROKEN
  FAIL_TRAY_APP_MODIFIED
  FAIL_USER_SETTINGS_MODIFIED
  FAIL_STASH_CHANGED
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

P = "\033[32m[PASS]\033[0m"
W = "\033[33m[WARN]\033[0m"
F = "\033[31m[FAIL]\033[0m"

issues, warnings, passes = [], [], []


def fail(code, msg): issues.append(f"{F} {code} — {msg}")
def warn(code, msg): warnings.append(f"{W} {code} — {msg}")
def ok(msg):         passes.append(f"{P} {msg}")


SECRET_TOKENS = (
    "device_token", "registration_code", "bearer", "cookie",
    "authorization", "api_key", "password",
)

ML = ROOT / "desktop/main_launcher.py"
WV = ROOT / "desktop/webview_app_pywebview.py"

ml_src = ML.read_text(encoding="utf-8")
wv_src = WV.read_text(encoding="utf-8")


# 1. main_launcher ↔ _check_consent 연결
if "from desktop.webview_app_pywebview import _check_consent" in ml_src \
        or "webview_app_pywebview._check_consent" in ml_src:
    ok("main_launcher 에서 _check_consent 임포트/참조 확인")
else:
    fail("FAIL_CONSENT_DIALOG_NOT_CONNECTED",
         "main_launcher 가 _check_consent 를 참조하지 않음")

if "run_consent_flow" in ml_src and "consent_state.get(\"agreed\")" in ml_src:
    ok("main() 흐름이 동의 거부 시 차단하도록 연결됨")
else:
    fail("FAIL_DECLINE_DOES_NOT_BLOCK",
         "main() 흐름이 consent decline 차단 로직 미연결")


# 2. secret leak (prompt 본문 + 저장 schema)
try:
    from desktop import webview_app_pywebview as web
    prompt_low = web.CONSENT_PROMPT_TEXT.lower()
    leaked = [s for s in SECRET_TOKENS if s in prompt_low]
    if leaked:
        fail("FAIL_CONSENT_SECRET_LEAK",
             f"동의 prompt 에 금칙어 발견: {leaked}")
    else:
        ok("동의 prompt 에 secret 키 없음")
except Exception as e:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN",
         f"webview_app_pywebview import 실패: {type(e).__name__}: {e}")


# 3. 저장 schema 안전성
import json as _json
import tempfile

try:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "data").mkdir()
        from desktop import webview_app_pywebview as web
        orig = web._consent_file_path
        web._consent_file_path = lambda: tdp / "data" / "consent.json"  # type: ignore
        try:
            web._save_consent(True)
            data = _json.loads((tdp / "data" / "consent.json").read_text(encoding="utf-8"))
        finally:
            web._consent_file_path = orig  # type: ignore

    allowed = {"agreed", "agreed_at", "version", "scope"}
    if not set(data.keys()).issubset(allowed):
        fail("FAIL_CONSENT_FILE_SCHEMA_UNSAFE",
             f"consent.json keys outside allowed set: {sorted(data.keys())}")
    elif any(t in _json.dumps(data).lower() for t in SECRET_TOKENS):
        fail("FAIL_CONSENT_SECRET_LEAK", "consent.json 에 금칙어 직렬화됨")
    else:
        ok("consent.json schema 안전 (agreed/agreed_at/version/scope)")
except Exception as e:
    fail("FAIL_CONSENT_FILE_SCHEMA_UNSAFE",
         f"_save_consent 검증 실패: {type(e).__name__}: {e}")


# 4. HAEHAN_SKIP_GUI 동작
try:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "data").mkdir()
        from desktop import webview_app_pywebview as web
        orig = web._consent_file_path
        web._consent_file_path = lambda: tdp / "data" / "consent.json"  # type: ignore
        os.environ["HAEHAN_SKIP_GUI"] = "1"
        tk_called = {"n": 0}
        orig_tk = web._default_tk_dialog_runner

        def _no_tk():
            tk_called["n"] += 1
            raise AssertionError("tk should not be called")
        web._default_tk_dialog_runner = _no_tk  # type: ignore
        try:
            res = web._check_consent()
        finally:
            web._default_tk_dialog_runner = orig_tk  # type: ignore
            web._consent_file_path = orig  # type: ignore
            os.environ.pop("HAEHAN_SKIP_GUI", None)

    if tk_called["n"] == 0 and res is False:
        ok("HAEHAN_SKIP_GUI=1 — tkinter 미호출 + 자동 거부")
    else:
        fail("FAIL_SKIP_GUI_BROKEN",
             f"SKIP_GUI 분기 오류: tk_called={tk_called['n']} result={res}")
except Exception as e:
    fail("FAIL_SKIP_GUI_BROKEN", f"{type(e).__name__}: {e}")


# 5. 기존 entrypoint 보존 (webview main 함수가 여전히 _check_consent 호출)
if "_check_consent()" in wv_src and "def main()" in wv_src:
    ok("webview main() 의 _check_consent 호출 유지")
else:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN",
         "webview_app_pywebview.main() 의 _check_consent 호출 누락")

# 기존 admin/whoami 흐름 보존 점검 (lazy import 보존)
if "from desktop import admin_webview" in ml_src and "from desktop import tray_runtime" in ml_src:
    ok("admin_mode lazy / tray_runtime 보존")
else:
    fail("FAIL_EXISTING_ENTRYPOINT_BROKEN",
         "admin_webview / tray_runtime 진입점 손상")


# 6. 보호 파일 미수정
def _git_diff(path: str) -> bool:
    r = subprocess.run(["git", "diff", "--name-only", "HEAD", path],
                       cwd=str(ROOT), capture_output=True, text=True)
    return bool(r.stdout.strip())


if _git_diff("desktop/tray_app.py"):
    fail("FAIL_TRAY_APP_MODIFIED", "desktop/tray_app.py 수정 감지")
else:
    ok("desktop/tray_app.py 미수정")

if _git_diff("desktop/user_settings.py"):
    fail("FAIL_USER_SETTINGS_MODIFIED", "desktop/user_settings.py 수정 감지")
else:
    ok("desktop/user_settings.py 미수정")


# 7. stash@{0} 유지
try:
    r = subprocess.run(["git", "stash", "list"],
                       cwd=str(ROOT), capture_output=True, text=True)
    stash_lines = [l for l in r.stdout.splitlines() if l.strip()]
    if stash_lines and "pre-whoami-route-session-leftover" in stash_lines[0]:
        ok("stash@{0} 유지 (pre-whoami-route-session-leftover)")
    else:
        fail("FAIL_STASH_CHANGED",
             f"stash@{{0}} 변경 감지: head={stash_lines[0] if stash_lines else 'EMPTY'}")
except Exception as e:
    warn("WARN_STASH_CHECK", f"stash 검사 실패: {e}")


# ── 결과 ────────────────────────────────────────────────────────────────
print()
print("=" * 68)
print("  HAEHAN_CONSENT_DIALOG_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_CONSENT_DIALOG\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
