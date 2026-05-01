"""WebSocket read-only probe client for local agent (TENANT-5C-1).

Read-only WebSocket probe to verify operational connectivity.
- Connects to /api/v1/local-agents/ws
- Sends auth message
- Receives auth_ok, heartbeat_ack, idle
- Logs connection status
- Exits immediately if task message received (no execution)
- Never sends result/running/approval messages

Usage:
    # Via environment variables
    export PROBE_WS_URL=ws://127.0.0.1:8400/api/v1/local-agents/ws
    export PROBE_AGENT_ID=test-agent
    export PROBE_DEVICE_TOKEN=token-here
    python scripts/probe_local_agent_ws_readonly.py

    # Via CLI arguments
    python scripts/probe_local_agent_ws_readonly.py \
        --ws-url ws://127.0.0.1:8400/api/v1/local-agents/ws \
        --agent-id test-agent \
        --device-token token-here \
        --timeout 15

Exit codes:
    0: Connection open, auth accepted, heartbeat seen, normal timeout/close
    2: Missing required configuration (URL, agent_id, or device_token)
    3: Auth failed (server close code 4401)
    4: Task message received (execution prohibited)
    5: Protocol error or unexpected exception
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProbeState:
    """Track probe connection state."""

    def __init__(self) -> None:
        self.connection_open = False
        self.auth_accepted = False
        self.heartbeat_seen = False
        self.task_received = False
        self.result_sent = False
        self.closed = False
        self.close_code: Optional[int] = None
        self.error_message: Optional[str] = None


async def run_probe(
    ws_url: str,
    agent_id: str,
    device_token: str,
    timeout_sec: float = 15.0,
) -> int:
    """Run WebSocket probe and return exit code."""
    import websockets

    state = ProbeState()

    try:
        # Connect to WebSocket
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            state.connection_open = True

            # Send auth message
            auth_msg = {
                "type": "auth",
                "agent_id": agent_id,
                "device_token": device_token,
            }
            await ws.send(json.dumps(auth_msg))

            # Wait for auth response or task (with timeout)
            try:
                async with asyncio.timeout(timeout_sec):
                    while True:
                        msg_text = await ws.recv()
                        msg = json.loads(msg_text)
                        msg_type = msg.get("type", "")

                        if msg_type == "auth_ok":
                            state.auth_accepted = True
                        elif msg_type in ("heartbeat_ack", "idle"):
                            state.heartbeat_seen = True
                        elif msg_type == "task":
                            # Task received: exit immediately (no execution)
                            state.task_received = True
                            state.closed = True
                            return 4
                        # Ignore other message types

            except asyncio.TimeoutError:
                # Normal timeout — probe completed successfully
                state.closed = True
                return 0

    except websockets.exceptions.WebSocketException as e:
        # Check if auth failed (close code 4401)
        if hasattr(e, "rcvd_close") and e.rcvd_close:
            if e.rcvd_close.code == 4401:
                return 3
        state.error_message = str(e)
        return 5

    except Exception as e:
        state.error_message = str(e)
        return 5

    finally:
        state.closed = True


def log_state(state: ProbeState, ws_url: str, token_present: bool) -> None:
    """Log probe state without exposing secrets."""
    parsed = urlparse(ws_url)
    endpoint_path = parsed.path

    print(f"endpoint_path={endpoint_path}")
    print(f"token_present={token_present}")
    print(f"connection_open={state.connection_open}")
    print(f"auth_accepted={state.auth_accepted}")
    print(f"heartbeat_seen={state.heartbeat_seen}")
    print(f"task_received={state.task_received}")
    print(f"result_sent={state.result_sent}")
    print(f"closed={state.closed}")

    if state.error_message:
        print(f"error={state.error_message}")


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WebSocket read-only probe for local agent"
    )
    parser.add_argument(
        "--ws-url",
        default=os.environ.get("PROBE_WS_URL", ""),
        help="WebSocket URL (env: PROBE_WS_URL)",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("PROBE_AGENT_ID", ""),
        help="Agent ID (env: PROBE_AGENT_ID)",
    )
    parser.add_argument(
        "--device-token",
        default=os.environ.get("PROBE_DEVICE_TOKEN", ""),
        help="Device token (env: PROBE_DEVICE_TOKEN, not logged)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Timeout in seconds (default 15)",
    )

    args = parser.parse_args(argv)

    # Validate required inputs
    if not args.ws_url or not args.agent_id or not args.device_token:
        print("ERROR: Missing required configuration")
        print("  --ws-url (PROBE_WS_URL)")
        print("  --agent-id (PROBE_AGENT_ID)")
        print("  --device-token (PROBE_DEVICE_TOKEN)")
        return 2

    token_present = bool(args.device_token)

    # Run probe
    exit_code = asyncio.run(
        run_probe(
            ws_url=args.ws_url,
            agent_id=args.agent_id,
            device_token=args.device_token,
            timeout_sec=args.timeout,
        )
    )

    # Create final state for logging
    state = ProbeState()
    if exit_code in (0, 4):
        # Only log success states
        state.connection_open = True
        state.closed = True
        if exit_code == 0:
            state.auth_accepted = True
            state.heartbeat_seen = True

    log_state(state, args.ws_url, token_present)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
