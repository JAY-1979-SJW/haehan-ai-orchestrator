"""audit_haehan_legacy_entrypoint_guard.py
HAEHAN_LEGACY_ENTRYPOINT_GUARD_01 감리.

baseline 이후 구버전 Agent/Electron/webview 경로가 재출현하거나
문서/스크립트에서 다시 정식 경로로 안내되는 것을 차단한다.

Verdicts:
  PASS_HAEHAN_LEGACY_ENTRYPOINT_GUARD
  FAIL_OFFICIAL_ENTRYPOINT_BROKEN
  FAIL_WEBVIEW_DIRECT_MAIN_GUIDED
  FAIL_AGENT_SPEC_BUILD_GUIDED
  FAIL_LEGACY_DIST_RESURRECTED
  FAIL_LEGACY_ELECTRON_RESURRECTED
  FAIL_UI_DIST_BACKUP_RESURRECTED
  FAIL_WEBVIEW_APP_DIRECT_GUIDED
  FAIL_BASELINE_DOC_MISSING_FIELDS
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


SECRET_TOKENS = ("device_token", "registration_code", "bearer", "cookie",
                 "authorization", "api_key", "password")

LAUNCHER = ROOT / "build/webview_launcher.py"
BASELINE = ROOT / "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md"


def _code_only(src: str) -> str:
    out, in_doc = [], False
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


# 1. 정식 entrypoint
launcher_src = LAUNCHER.read_text(encoding="utf-8") if LAUNCHER.exists() else ""
launcher_code = _code_only(launcher_src)
if "from desktop.main_launcher import main" in launcher_code:
    ok("build/webview_launcher.py = desktop.main_launcher.main")
else:
    fail("FAIL_OFFICIAL_ENTRYPOINT_BROKEN",
         "launcher 가 main_launcher 를 import 하지 않음")

if "from desktop.webview_app_pywebview import main" in launcher_code \
        or "webview_app_pywebview.main(" in launcher_code:
    fail("FAIL_WEBVIEW_DIRECT_MAIN_GUIDED",
         "launcher 코드에 webview_app_pywebview.main 직접 호출 잔존")
else:
    ok("launcher 코드 = webview_app_pywebview.main 직접 호출 없음")


# 2. legacy 산출물/소스 디렉터리 재출현 금지
def _exists(p: str) -> bool:
    return (ROOT / p).exists()


if _exists("dist/HaehanAI-Agent"):
    fail("FAIL_LEGACY_DIST_RESURRECTED", "dist/HaehanAI-Agent/ 재출현")
else:
    ok("dist/HaehanAI-Agent/ 부재")

if _exists("desktop/electron"):
    fail("FAIL_LEGACY_ELECTRON_RESURRECTED", "desktop/electron/ 재출현")
else:
    ok("desktop/electron/ 부재")

backup_dirs = list((ROOT / "desktop").glob("ui_dist_backup_*"))
if backup_dirs:
    fail("FAIL_UI_DIST_BACKUP_RESURRECTED",
         f"ui_dist_backup_* 재출현: {[d.name for d in backup_dirs]}")
else:
    ok("desktop/ui_dist_backup_* 부재")


# 3. 문서/스크립트에서 legacy 경로를 정식으로 안내하는지 검사
# scan target: 운영 문서, 운영 스크립트 (ops/), CLAUDE.md 등 — 단, baseline 문서
# 와 본 audit/test 자체는 legacy 키워드를 '금지 대상'으로 언급하므로 예외 처리.

ALLOW_LEGACY_MENTION = {
    "docs/release/HAEHAN_DESKTOP_RELEASE_BASELINE_01.md",
    "scripts/ops/audit_haehan_legacy_entrypoint_guard.py",
    "scripts/ops/audit_haehan_desktop_release_baseline.py",
    "scripts/ops/audit_haehan_single_exe_build.py",
    "scripts/ops/audit_haehan_consent_dialog.py",
    "tests/test_haehan_legacy_entrypoint_guard.py",
    "tests/test_haehan_single_exe_build_entrypoint.py",
    "tests/test_haehan_consent_dialog.py",
    # build/spec 자체 (실제 entrypoint 정의 위치)
    "build/webview_launcher.py",
    "HaehanAI-Desktop.spec",
    # 본 작업 이전에 작성된 legacy 자체 source
    "desktop/webview_app.py",
    "desktop/webview_app_pywebview.py",
}


def _scan_text(rel: Path, text: str) -> None:
    rel_str = rel.as_posix()
    if rel_str in ALLOW_LEGACY_MENTION:
        return
    # 1) HaehanAI-Agent.spec 빌드 안내
    if re.search(r"(pyinstaller|PyInstaller)[^\n]{0,80}HaehanAI-Agent\.spec",
                 text, re.IGNORECASE):
        fail("FAIL_AGENT_SPEC_BUILD_GUIDED",
             f"{rel_str} 가 HaehanAI-Agent.spec 빌드 명령을 안내")
    # 2) webview_app.py 직접 실행 안내
    if re.search(r"python\s+-m\s+desktop\.webview_app\b(?!_pywebview)", text):
        fail("FAIL_WEBVIEW_APP_DIRECT_GUIDED",
             f"{rel_str} 가 desktop.webview_app 직접 실행을 정식 안내")
    # 3) webview_app_pywebview.main() 직접 호출 안내 (코드/문서)
    if "webview_app_pywebview.main()" in text \
            and "직접 호출" not in text and "직접 실행" not in text:
        # 안내 vs 금지 컨텍스트는 구분 어려움 → 보수적 WARN
        # baseline/audit/test 는 ALLOW_LEGACY_MENTION 으로 제외됨
        warn("WARN_WEBVIEW_DIRECT_MAIN_MENTION",
             f"{rel_str} 에 webview_app_pywebview.main() 문자열 존재 — 안내 의도인지 확인")


# scan docs/* + scripts/ops/* + CLAUDE.md
scan_paths = [ROOT / "CLAUDE.md", ROOT / "README.md"]
for d in ("docs", "scripts/ops", "scripts"):
    p = ROOT / d
    if not p.exists():
        continue
    for ext in ("*.md", "*.py", "*.txt"):
        scan_paths.extend(p.rglob(ext))

for sp in scan_paths:
    try:
        rel = sp.relative_to(ROOT)
    except Exception:
        continue
    if not sp.is_file():
        continue
    try:
        text = sp.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    _scan_text(rel, text)

ok("문서/스크립트 legacy 안내 패턴 스캔 완료")


# 4. baseline 문서 필수 필드 (정식 exe 경로 + sha256)
if not BASELINE.exists():
    fail("FAIL_BASELINE_DOC_MISSING_FIELDS",
         "release baseline 문서 부재")
else:
    bt = BASELINE.read_text(encoding="utf-8")
    need = [
        "dist/HaehanAI-Desktop/HaehanAI-Desktop.exe",
        "SHA-256",
    ]
    miss = [k for k in need if k not in bt]
    if miss:
        fail("FAIL_BASELINE_DOC_MISSING_FIELDS",
             f"baseline 문서 필수 필드 누락: {miss}")
    else:
        ok("baseline 문서 정식 exe 경로 + SHA-256 기재 확인")
    # 문서 자체 secret 노출 검사
    low = bt.lower()
    leaks = [t for t in SECRET_TOKENS
             if re.search(rf"\b{t}\s*[=:]\s*['\"][^'\"\n]+['\"]", low)]
    if leaks:
        fail("FAIL_SECRET_LEAK",
             f"baseline 문서에 secret 값 노출: {leaks}")


# 5. 보호 파일 미수정
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
print("  HAEHAN_LEGACY_ENTRYPOINT_GUARD_01 감리")
print("=" * 68)
for p in passes:   print(p)
for w in warnings: print(w)
for i in issues:   print(i)
print("-" * 68)
print(f"PASS: {len(passes)}  WARN: {len(warnings)}  FAIL: {len(issues)}")
if not issues:
    print(f"\033[32m✅ PASS_HAEHAN_LEGACY_ENTRYPOINT_GUARD\033[0m")
else:
    print(f"\033[31m❌ FAIL — {len(issues)}건 수정 필요\033[0m")
print("=" * 68)
sys.exit(1 if issues else 0)
