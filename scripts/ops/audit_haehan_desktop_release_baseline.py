"""audit_haehan_desktop_release_baseline.py
HAEHAN_DESKTOP_RELEASE_BASELINE_01 감리.

Verdicts:
  PASS_HAEHAN_DESKTOP_RELEASE_BASELINE
  FAIL_BASELINE_DOC_MISSING
  FAIL_BASELINE_DOC_INCOMPLETE
  FAIL_OFFICIAL_EXE_MISSING
  FAIL_OFFICIAL_ENTRYPOINT_WRONG
  FAIL_LEGACY_DIST_RESURRECTED
  FAIL_LEGACY_ELECTRON_RESURRECTED
  FAIL_SMOKE_RECORD_MISSING
  FAIL_SECRET_LEAK
  FAIL_FORBIDDEN_FILE_MODIFIED
  FAIL_STASH_CHANGED
"""
from __future__ import annotations

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


DOC = ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md"
EXE = ROOT / "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe"
LAUNCHER = ROOT / "build/webview_launcher.py"

SECRET_TOKENS = ("device_token", "registration_code", "bearer", "cookie",
                 "authorization", "api_key", "password")


# 1. baseline 문서
if not DOC.exists():
    fail("FAIL_BASELINE_DOC_MISSING", f"{DOC.relative_to(ROOT)} 부재")
else:
    text = DOC.read_text(encoding="utf-8")
    required = [
        "HaehanAI-Desktop.exe",
        "desktop.main_launcher.main",
        "HAEHAN_SKIP_GUI",
        "HAEHAN_ROLE",
        "dist/HaehanAI-Agent",
        "desktop/electron",
        "desktop/webview_app.py",
        "rc=4",
        "stash@{0}",
    ]
    missing = [k for k in required if k not in text]
    if missing:
        fail("FAIL_BASELINE_DOC_INCOMPLETE",
             f"필수 항목 누락: {missing}")
    else:
        ok("baseline 문서 필수 항목 모두 기재")

    # smoke 표/결과 단어가 있는지
    if "Smoke" in text and "rc=4" in text and "마스킹" in text:
        ok("smoke 기준 결과 표 존재")
    else:
        fail("FAIL_SMOKE_RECORD_MISSING", "smoke 결과 기록이 문서에서 식별 불가")

    # secret 원문이 문서에 노출되지 않았는지
    low = text.lower()
    leaks = [t for t in SECRET_TOKENS
             if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"\n]+['\"]", low)]
    if leaks:
        fail("FAIL_SECRET_LEAK", f"baseline 문서에 secret 값 노출: {leaks}")
    else:
        ok("baseline 문서 secret 값 노출 없음")


# 2. 정식 exe 존재
if not EXE.exists():
    fail("FAIL_OFFICIAL_EXE_MISSING", f"{EXE.relative_to(ROOT)} 부재")
else:
    ok(f"정식 exe 존재 ({EXE.stat().st_size / (1024 * 1024):.1f} MB)")


# 3. entrypoint
if LAUNCHER.exists():
    src = LAUNCHER.read_text(encoding="utf-8")
    if "from desktop.main_launcher import main" in src:
        ok("정식 entrypoint = desktop.main_launcher.main")
    else:
        fail("FAIL_OFFICIAL_ENTRYPOINT_WRONG",
             "build/webview_launcher.py 가 main_launcher 를 import 하지 않음")
else:
    fail("FAIL_OFFICIAL_ENTRYPOINT_WRONG", "build/webview_launcher.py 부재")


# 4. legacy 부활 여부
if (ROOT / "dist/HaehanAI-Agent").exists():
    fail("FAIL_LEGACY_DIST_RESURRECTED",
         "dist/HaehanAI-Agent/ 재출현 — baseline 위배")
else:
    ok("dist/HaehanAI-Agent/ 부재 (legacy dist 미부활)")

if (ROOT / "desktop/electron").exists():
    fail("FAIL_LEGACY_ELECTRON_RESURRECTED",
         "desktop/electron/ 재출현 — baseline 위배")
else:
    ok("desktop/electron/ 부재 (legacy electron 미부활)")

# legacy source 는 보존되어야 함
if (ROOT / "desktop/webview_app.py").exists():
    ok("desktop/webview_app.py legacy source 보존")
else:
    fail("FAIL_FORBIDDEN_FILE_MODIFIED",
         "desktop/webview_app.py 삭제됨 — baseline 위배")


# 5. 보호 파일 미수정
def _diff(p: str) -> bool:
    r = subprocess.run(["git", "diff", "--name-only", "HEAD", p],
                       cwd=str(ROOT), capture_output=True, text=True)
    return bool(r.stdout.strip())


for p in ("desktop/tray_app.py", "desktop/user_settings.py",
          "desktop/webview_app.py"):
    if _diff(p):
        fail("FAIL_FORBIDDEN_FILE_MODIFIED", f"{p} 수정 감지")
    else:
        ok(f"{p} 미수정")


# 6. stash@{0}
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
print("  HAEHAN_DESKTOP_RELEASE_BASELINE_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_DESKTOP_RELEASE_BASELINE\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
