"""git hook 설치 스크립트.

.git/hooks/pre-commit  — ruff 문법/품질 검사 (staged 파일만)
.git/hooks/pre-push    — Claude Code AI 코드 검수

실행:
  python scripts/ops/install_git_hooks.py
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # scripts/ops/ → repo root
# core.hooksPath = .githooks (프로젝트 설정)
HOOKS_DIR = ROOT / ".githooks"

PRE_COMMIT = """\
#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .githooks/ 는 repo root 바로 아래

# staged .py 파일 목록
r = subprocess.run(
    ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
    cwd=str(ROOT), capture_output=True, text=True,
)
py_files = [f for f in r.stdout.splitlines() if f.endswith(".py")]

if py_files:
    cfg = str(ROOT / "configs" / "ruff.toml")
    # 1. ruff check (자동 수정 + 수정 불가 오류는 FAIL)
    check = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", "--config", cfg] + py_files,
        cwd=str(ROOT),
    )
    # 2. ruff format
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--config", cfg] + py_files,
        cwd=str(ROOT),
    )
    # ruff check 이 수정한 파일을 다시 stage
    subprocess.run(["git", "add"] + py_files, cwd=str(ROOT))
    if check.returncode != 0:
        print("[ruff] 수정 불가 오류가 있습니다. 위 내용을 확인하고 재커밋하세요.")
        sys.exit(1)

# ── 로그인 세션 파기 코드 차단 ───────────────────────────────────────
# 세션을 임의 로그아웃/쿠키삭제하면 '매번 재로그인' 문제 발생(CLAUDE.md 로그인 세션 보존).
# staged .py 에 세션 파기 패턴이 추가되면 차단. 정당한 로그아웃이면 줄에 '# session-ok'.
# (이 훅 설치 파일 자신은 패턴을 데이터로 가지므로 제외)
_sg_files = [f for f in py_files if not f.endswith("install_git_hooks.py")]
if _sg_files:
    _sdiff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--"] + _sg_files,
        cwd=str(ROOT), capture_output=True, text=True,
    )
    _sess_pat = (
        "nidlogin.logout", "logout.naver", "clear_cookies", "delete_cookies",
        "deleteallcookies", "cookies.clear", "context.clear_cookies",
    )
    _sess_bad = []
    for _ln in _sdiff.stdout.splitlines():
        if _ln.startswith("+") and not _ln.startswith("+++"):
            _body = _ln[1:]
            if "session-ok" in _body:
                continue
            _low = _body.lower()
            if any(_pp in _low for _pp in _sess_pat):
                _sess_bad.append(_body.strip())
    if _sess_bad:
        print("=" * 60)
        print("[session-guard] 로그인 세션 파기 코드 감지 — 매번 재로그인 유발:")
        for _b in _sess_bad[:8]:
            print("    + " + _b[:90])
        print("    세션은 유지해야 합니다(CLAUDE.md 로그인 세션 보존).")
        print("    정당한 로그아웃이면 해당 줄에 '# session-ok' 주석을 추가하세요.")
        print("=" * 60)
        sys.exit(1)

# ── 소스 실행 방식 강제 ──────────────────────────────────────────────
# launcher(start_haehan_ai.ps1)가 frozen exe / Next standalone 빌드본을 '실행'하면 차단.
# 백엔드=uvicorn 소스, 프론트=next dev 소스 유지(재빌드 불필요). 정당한 예외는 파일에 '# source-ok'.
all_staged = r.stdout.splitlines()
if "scripts/start_haehan_ai.ps1" in all_staged:
    try:
        _txt = (ROOT / "scripts" / "start_haehan_ai.ps1").read_text(encoding="utf-8", errors="replace")
    except Exception:
        _txt = ""
    if "# source-ok" not in _txt:
        _bad = []
        if "Start-Process $FASTAPI" in _txt:
            _bad.append("FastAPI를 frozen exe로 실행 — uvicorn 소스로 유지하세요")
        if "-ArgumentList $NEXTJS" in _txt:
            _bad.append("Next를 standalone 빌드본(server.js)으로 실행 — next dev 소스로 유지하세요")
        if "uvicorn" not in _txt:
            _bad.append("uvicorn(소스 백엔드) 실행 흔적이 없습니다")
        if '"dev"' not in _txt:
            _bad.append("next dev(소스 프론트) 실행 흔적이 없습니다")
        if _bad:
            print("=" * 60)
            print("[source-only] launcher가 소스 실행 방식을 벗어났습니다 (재빌드 금지):")
            for _b in _bad:
                print("    - " + _b)
            print("    백엔드=uvicorn 소스, 프론트=next dev 소스로 유지하세요.")
            print("    정당한 예외면 start_haehan_ai.ps1 에 '# source-ok' 주석을 추가하세요.")
            print("=" * 60)
            sys.exit(1)

# 기존 quality gate (pre-commit 내장)
from pathlib import Path as _P
import importlib.util, os
gate = ROOT / "scripts" / "quality_gate.py"
if gate.exists():
    result = subprocess.run(
        [sys.executable, str(gate), "--staged", "--enforce", "--allow-existing-code-change"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)
"""

PRE_PUSH = """\
#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .githooks/ 는 repo root 바로 아래

# Claude Code AI 코드 검수
result = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "ops" / "ai_code_review_gate.py")],
    cwd=str(ROOT),
)
sys.exit(result.returncode)
"""


def install(name: str, content: str) -> None:
    path = HOOKS_DIR / name
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[install_git_hooks] {name} 설치 완료: {path}")


def main() -> None:
    if not HOOKS_DIR.exists():
        print(f"[install_git_hooks] .git/hooks 디렉터리를 찾을 수 없습니다: {HOOKS_DIR}")
        sys.exit(1)
    install("pre-commit", PRE_COMMIT)
    install("pre-push", PRE_PUSH)
    print("[install_git_hooks] 완료. pre-commit(ruff) + pre-push(AI 검수) 활성화됨.")


if __name__ == "__main__":
    main()
