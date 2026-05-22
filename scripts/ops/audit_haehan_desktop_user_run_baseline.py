"""audit_haehan_desktop_user_run_baseline.py
HAEHAN_DESKTOP_USER_RUN_BASELINE_01 감리.

Verdicts:
  PASS_HAEHAN_DESKTOP_USER_RUN_BASELINE
  FAIL_USER_RUN_DOC_MISSING
  FAIL_USER_RUN_DOC_INCOMPLETE
  FAIL_USER_RUN_DOC_SHA_MISMATCH
  FAIL_SECRET_LEAK
  FAIL_FORBIDDEN_FILE_MODIFIED
  FAIL_STASH_CHANGED
"""
from __future__ import annotations

import hashlib
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

DOC = ROOT / "docs/release/HAEHAN_DESKTOP_USER_RUN_BASELINE_01.md"
EXE = ROOT / "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe"
BUILD_BASELINE = ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md"


# 1. 문서 존재 + 필수 항목
if not DOC.exists():
    fail("FAIL_USER_RUN_DOC_MISSING", f"{DOC.relative_to(ROOT)} 부재")
else:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe",   # exe 경로
        "SHA-256",                                       # SHA 라벨
        "HaehanAI 0.2.0-launcher-foundation",            # version
        "rc=4",                                          # consent 차단
        "rc=2",                                          # admin 차단
        "rc=0",                                          # 허용
        "agent_id_masked",                               # diag masking
        "server.url_redacted",
        "dist/HaehanAI-Agent",                           # legacy 부재 기록
        "desktop/electron",
        "ui_dist_backup",
        "290 passed",                                    # 테스트 기록
        "CDP",                                           # CDP 유지 기록
        "HAEHAN_ROLE",
        "HAEHAN_SKIP_GUI",
        "stash@{0}",
        "사전",                                          # 실행 전 상태
        "잔류",                                          # 실행 후 상태
        "audit_haehan_single_exe_build",
        "audit_haehan_consent_dialog",
        "audit_haehan_whoami_route",
        "audit_haehan_admin_mode_webview_lazy_load",
        "audit_haehan_tray_registration_merge",
        "audit_haehan_desktop_release_baseline",
        "audit_haehan_legacy_entrypoint_guard",
    ]
    missing = [k for k in required if k not in text]
    if missing:
        fail("FAIL_USER_RUN_DOC_INCOMPLETE",
             f"필수 항목 누락: {missing}")
    else:
        ok("user-run baseline 문서 필수 항목 모두 기재")

    # SHA hex 64자 정확 일치
    m = re.search(r"\b([0-9a-f]{64})\b", text)
    if not m:
        fail("FAIL_USER_RUN_DOC_INCOMPLETE", "SHA-256 hex 누락")
    else:
        recorded = m.group(1)
        if EXE.exists():
            actual = hashlib.sha256(EXE.read_bytes()).hexdigest()
            if recorded != actual:
                fail("FAIL_USER_RUN_DOC_SHA_MISMATCH",
                     f"기록 SHA {recorded[:16]}… ≠ 실측 {actual[:16]}…")
            else:
                ok(f"기록 SHA-256 == 실측 ({recorded[:12]}…)")
        else:
            warn("WARN_EXE_ABSENT", "exe 부재 — SHA 검증 생략")

        # 빌드 baseline 의 SHA 와 동일한지
        if BUILD_BASELINE.exists():
            bb = BUILD_BASELINE.read_text(encoding="utf-8")
            m2 = re.search(r"\b([0-9a-f]{64})\b", bb)
            if m2 and m2.group(1) == recorded:
                ok("user-run baseline SHA == release baseline SHA")
            elif m2:
                fail("FAIL_USER_RUN_DOC_SHA_MISMATCH",
                     f"build baseline SHA {m2.group(1)[:16]}… ≠ user-run baseline {recorded[:16]}…")

    # secret 실값 노출 검사
    low = text.lower()
    leaks = [t for t in SECRET_TOKENS
             if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"\n]+['\"]", low)]
    if leaks:
        fail("FAIL_SECRET_LEAK", f"user-run 문서 secret 값 노출: {leaks}")
    else:
        ok("user-run 문서 secret 값 노출 없음")


# 2. 보호 파일
def _diff(p: str) -> bool:
    r = subprocess.run(["git", "diff", "--name-only", "HEAD", p],
                       cwd=str(ROOT), capture_output=True, text=True)
    return bool(r.stdout.strip())


for p in ("desktop/tray_app.py", "desktop/user_settings.py",
          "desktop/webview_app.py", "desktop/webview_app_pywebview.py",
          "desktop/main_launcher.py"):
    if _diff(p):
        fail("FAIL_FORBIDDEN_FILE_MODIFIED", f"{p} 수정 감지")
    else:
        ok(f"{p} 미수정")


# 3. stash@{0}
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
print("  HAEHAN_DESKTOP_USER_RUN_BASELINE_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_DESKTOP_USER_RUN_BASELINE\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
