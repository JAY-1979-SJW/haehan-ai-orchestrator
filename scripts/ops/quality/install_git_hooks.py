"""Install repository-local Git hooks."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOKS_DIR = ROOT / ".githooks"
PRE_COMMIT = HOOKS_DIR / "pre-commit"


def main() -> int:
    if not PRE_COMMIT.exists():
        print("FAIL: .githooks/pre-commit missing")
        return 1
    result = subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        encoding="utf-8",
    )
    if result.returncode != 0:
        print((result.stdout or "").strip() or "FAIL: git config core.hooksPath failed")
        return result.returncode
    print("PASS: core.hooksPath=.githooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
