"""Shared guard for browser launches in sandboxed agent runtimes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

SANDBOX_ENV_MARKERS = (
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CODEX_THREAD_ID",
    "CODEX_MANAGED_BY_NPM",
    "HAEHAN_NO_BROWSER_LAUNCH",  # 검증·CI 실행 중(verify_change 등) — 테스트가 실제 브라우저를 띄우지 않게
)

SANDBOX_BROWSER_LAUNCH_BLOCKED = "sandbox_browser_launch_blocked"


def is_sandboxed_runtime() -> bool:
    return any(os.environ.get(name) for name in SANDBOX_ENV_MARKERS)


def sandbox_block_payload(*, component: str, action: str = "browser_launch") -> dict[str, Any]:
    return {
        "ok": False,
        "code": SANDBOX_BROWSER_LAUNCH_BLOCKED,
        "component": component,
        "action": action,
        "message": (
            "Browser launch is blocked inside the sandbox. "
            "Start or keep the browser outside the sandbox, then attach/inspect only."
        ),
        "markers": [name for name in SANDBOX_ENV_MARKERS if os.environ.get(name)],
    }


def assert_browser_launch_allowed(*, component: str, action: str = "browser_launch") -> None:
    if not is_sandboxed_runtime():
        return
    raise RuntimeError(json.dumps(sandbox_block_payload(component=component, action=action), ensure_ascii=False))


__all__ = [
    "SANDBOX_BROWSER_LAUNCH_BLOCKED",
    "assert_browser_launch_allowed",
    "is_sandboxed_runtime",
    "sandbox_block_payload",
]
