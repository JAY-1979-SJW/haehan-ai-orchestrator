"""Install the repository quality gate as a local pre-commit hook."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".git" / "hooks" / "pre-commit"

HOOK_BODY = """#!/bin/sh
python scripts/quality_gate.py --staged --enforce
"""


def install() -> Path:
    if not (ROOT / ".git").exists():
        raise RuntimeError("not a git repository")
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(HOOK_BODY, encoding="utf-8")
    try:
        HOOK.chmod(0o755)
    except OSError:
        pass
    return HOOK


def main() -> None:
    path = install()
    print(f"quality gate hook installed: {path}")


if __name__ == "__main__":
    main()

