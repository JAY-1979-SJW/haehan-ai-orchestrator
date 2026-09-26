# module_category: audit
# primary_trade: common
"""PreToolUse 훅: verify_change/merge_stage 가 이미 실행 중이면 중복 실행을 deny(기준서 §5.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.pipeline_lock import describe, live_lock

TARGETS = {"verify_change.py": "verify", "merge_stage.py": "merge"}


def decide(command: str) -> str | None:
    for key, lock in TARGETS.items():
        if key in command:
            info = live_lock(lock)
            if info:
                return f"{key}: {describe(info)}"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    reason = decide(str((payload.get("tool_input") or {}).get("command", "")))
    if reason:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
