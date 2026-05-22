"""audit_haehan_desktop_install_shortcut.py
HAEHAN_DESKTOP_INSTALL_SHORTCUT_01 감리.

Verdicts:
  PASS_HAEHAN_DESKTOP_INSTALL_SHORTCUT
  FAIL_INSTALLER_SCRIPT_MISSING
  FAIL_OFFICIAL_EXE_MISSING
  FAIL_SHA_MISMATCH
  FAIL_LEGACY_PATH_NOT_BLOCKED
  FAIL_USER_RUN_DOC_MISMATCH
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

SCRIPT = ROOT / "scripts/haehan/create_desktop_shortcut.py"
EXE = ROOT / "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe"
RELEASE_DOC = ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md"
USER_RUN_DOC = ROOT / "docs/release/HAEHAN_DESKTOP_USER_RUN_BASELINE_01.md"


# 1. installer 스크립트 존재
if not SCRIPT.exists():
    fail("FAIL_INSTALLER_SCRIPT_MISSING", f"{SCRIPT.relative_to(ROOT)} 부재")
    print("[CRITICAL] installer 부재 — 후속 검사 생략")
    sys.exit(1)

ok("create_desktop_shortcut.py 존재")

src = SCRIPT.read_text(encoding="utf-8")

# legacy 차단 패턴 명시
required_patterns = [
    "HaehanAI-Agent.exe",
    "dist/HaehanAI-Agent",
    "desktop/electron",
    "desktop/webview_app.py",
    "LEGACY_PATTERNS",
    "is_legacy_target",
    "verify_official_exe",
    "baseline_sha256",
    "OFFICIAL_EXE_REL",
]
missing = [k for k in required_patterns if k not in src]
if missing:
    fail("FAIL_LEGACY_PATH_NOT_BLOCKED",
         f"installer 에 필수 가드 누락: {missing}")
else:
    ok("installer 가 legacy 경로 차단 패턴/검증 함수 모두 보유")

# is_legacy_target 동작 확인
sys.path.insert(0, str(ROOT))
from scripts.haehan import create_desktop_shortcut as shortcut  # noqa: E402

legacy_samples = [
    "dist/HaehanAI-Agent/HaehanAI-Agent.exe",
    "desktop/electron/main.js",
    "desktop/webview_app.py",
    r"C:\foo\dist\HaehanAI-Agent\app.exe",
]
not_blocked = [p for p in legacy_samples if not shortcut.is_legacy_target(p)]
if not_blocked:
    fail("FAIL_LEGACY_PATH_NOT_BLOCKED", f"legacy 미차단: {not_blocked}")
else:
    ok(f"legacy 경로 샘플 {len(legacy_samples)}개 전부 차단")

if shortcut.is_legacy_target("dist/HaehanAI-Desktop/HaehanAI-Desktop.exe"):
    fail("FAIL_LEGACY_PATH_NOT_BLOCKED",
         "정식 exe 가 legacy 로 잘못 분류됨")
else:
    ok("정식 exe 경로는 legacy 아님")


# 2. 공식 exe 존재 + SHA 일치
if not EXE.exists():
    fail("FAIL_OFFICIAL_EXE_MISSING", f"{EXE.relative_to(ROOT)} 부재")
else:
    ok("공식 exe 존재")
    expected = shortcut.baseline_sha256(ROOT)
    if not expected:
        fail("FAIL_SHA_MISMATCH", "release baseline 문서에서 SHA 추출 실패")
    else:
        actual = hashlib.sha256(EXE.read_bytes()).hexdigest()
        if actual != expected:
            fail("FAIL_SHA_MISMATCH",
                 f"기록 {expected[:16]}… ≠ 실측 {actual[:16]}…")
        else:
            ok(f"공식 exe SHA-256 일치 ({actual[:12]}…)")

        # user-run baseline 문서도 같은 SHA 인지 확인
        if USER_RUN_DOC.exists():
            m = re.search(r"\b([0-9a-f]{64})\b",
                          USER_RUN_DOC.read_text(encoding="utf-8"))
            if not m:
                fail("FAIL_USER_RUN_DOC_MISMATCH",
                     "user-run 문서에서 SHA 추출 실패")
            elif m.group(1) != actual:
                fail("FAIL_USER_RUN_DOC_MISMATCH",
                     f"user-run 문서 SHA {m.group(1)[:16]}… ≠ exe {actual[:16]}…")
            else:
                ok("user-run baseline SHA == exe 실측")


# 3. installer 자체 secret leak
low = src.lower()
leaks = [t for t in SECRET_TOKENS
         if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"\n]+['\"]", low)]
if leaks:
    fail("FAIL_SECRET_LEAK", f"installer 에 secret 값: {leaks}")
else:
    ok("installer secret 값 노출 없음")


# 4. 보호 파일 미수정
def _diff(p: str) -> bool:
    r = subprocess.run(["git", "diff", "--name-only", "HEAD", p],
                       cwd=str(ROOT), capture_output=True, text=True)
    return bool(r.stdout.strip())


for p in ("desktop/tray_app.py", "desktop/user_settings.py",
          "desktop/webview_app.py", "desktop/webview_app_pywebview.py",
          "desktop/main_launcher.py",
          "build/webview_launcher.py", "HaehanAI-Desktop.spec"):
    if _diff(p):
        fail("FAIL_FORBIDDEN_FILE_MODIFIED", f"{p} 수정 감지")
    else:
        ok(f"{p} 미수정")


# 5. legacy 경로 부재 (디렉터리)
for p in ("dist/HaehanAI-Agent", "desktop/electron"):
    if (ROOT / p).exists():
        fail("FAIL_LEGACY_PATH_NOT_BLOCKED", f"{p}/ 재출현")
    else:
        ok(f"{p}/ 부재")


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
print("  HAEHAN_DESKTOP_INSTALL_SHORTCUT_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_DESKTOP_INSTALL_SHORTCUT\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
