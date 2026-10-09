"""Install the repository quality gate as a local pre-commit hook."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
_BOOT = Path(__file__).resolve().parents[3]
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
HOOK = ROOT / ".git" / "hooks" / "pre-commit"

HOOK_BODY = """#!/bin/sh
python tools/quality/quality_gate.py --staged --enforce
python tools/audits/google/audit_google_home_login_gate.py
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
