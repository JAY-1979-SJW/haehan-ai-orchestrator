"""Compatibility wrapper for the archived read-only local-agent WS probe."""
from __future__ import annotations

# Compatibility marker for tests: the archived probe sends {"type": "auth"}.
from scripts.archive.one_off.probe_local_agent_ws_readonly import *  # noqa: F401,F403
from scripts.archive.one_off.probe_local_agent_ws_readonly import main as _main


if __name__ == "__main__":
    raise SystemExit(_main())
