"""git hook 설치 스크립트.

.git/hooks/pre-commit  — ruff 문법/품질 검사 (staged 파일만)
.git/hooks/pre-push    — Claude Code AI 코드 검수

실행:
  python scripts/ops/install_git_hooks.py
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / ".git" / "hooks"

PRE_COMMIT = """\
#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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

ROOT = Path(__file__).resolve().parents[2]

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
