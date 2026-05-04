#!/usr/bin/env python
"""표준 실행 wrapper for WebSocket controlled agent.

예:
    export LOCAL_AGENT_REGISTRATION_CODE=code-xxx-yyy-zzz
    python scripts/run_local_agent_ws_client.py --server-url http://127.0.0.1:8400

또는:
    python -m agent.local_agent_ws_runner --server-url http://127.0.0.1:8400 \
        --registration-code-env LOCAL_AGENT_REGISTRATION_CODE
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.local_agent_ws_runner import main

if __name__ == "__main__":
    sys.exit(main())
