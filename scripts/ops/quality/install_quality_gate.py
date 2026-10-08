"""Install the repository quality gate as a local pre-commit hook."""

from __future__ import annotations

import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / ".git" / "hooks" / "pre-commit"

HOOK_BODY = """#!/bin/sh
python scripts/ops/quality/quality_gate.py --staged --enforce
python scripts/ops/audit_google_home_login_gate.py
"""


def install() -> Path:
    if not (ROOT / ".git").exists():
        raise RuntimeError("not a git repository")
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(HOOK_BODY, encoding="utf-8")
    with contextlib.suppress(OSError):
        HOOK.chmod(0o755)
    return HOOK


def main() -> None:
    path = install()
    print(f"quality gate hook installed: {path}")


if __name__ == "__main__":
    main()
