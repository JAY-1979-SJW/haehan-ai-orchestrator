"""로컬 에이전트 WebSocket controlled runner (controlled connection smoke only).

등록 → WebSocket auth → heartbeat N회 → close 만 수행한다.
task 실행은 하지 않는다.

사용 예:
    export LOCAL_AGENT_REGISTRATION_CODE=code-xxx-yyy-zzz
    python -m agent.local_agent_ws_runner \
        --server-url http://127.0.0.1:8400 \
        --registration-code-env LOCAL_AGENT_REGISTRATION_CODE \
        --heartbeat-count 2
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def _register_with_code(
    server_url: str,
    registration_code: str,
    host: str,
    os_name: str,
    version: str,
) -> tuple[str, str]:
    """HTTP API를 사용해서 registration code로 agent를 등록.

    반환값: (agent_id, device_token)
    """
    try:
        import requests
    except ImportError:
        raise ImportError("requests library required")

    url = f"{server_url.rstrip('/')}/api/v1/local-agents/register-with-code"
    payload = {
        "registration_code": registration_code,
        "host": host,
        "os_name": os_name,
        "version": version,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        agent_id = data.get("agent_id")
        device_token = data.get("device_token")
        if not agent_id or not device_token:
            raise ValueError("Missing agent_id or device_token in response")
        return agent_id, device_token
    except Exception as e:
        raise RuntimeError(f"Failed to register with code: {e}")


def main(argv: Optional[list[str]] = None) -> int:
    """Runner main function."""
    parser = argparse.ArgumentParser(
        description="Local agent WebSocket controlled connection runner"
    )
    parser.add_argument(
        "--server-url",
        required=True,
        help="Server base URL (e.g., http://127.0.0.1:8400)",
    )
    parser.add_argument(
        "--registration-code-env",
        required=True,
        help="Environment variable name containing registration code",
    )
    parser.add_argument(
        "--heartbeat-count",
        type=int,
        default=2,
        help="Number of heartbeats to send (default 2)",
    )
    parser.add_argument(
        "--host",
        default="smoke-test-windows-pc",
        help="Agent hostname (default smoke-test-windows-pc)",
    )
    parser.add_argument(
        "--os-name",
        default="Windows",
        help="OS name (default Windows)",
    )
    parser.add_argument(
        "--version",
        default="ws-smoke",
        help="Agent version (default ws-smoke)",
    )
    parser.add_argument(
        "--no-task",
        action="store_true",
        default=True,
        help="Do not execute tasks (always true, ignored)",
    )
    parser.add_argument(
        "--allow-task-action",
        default="",
        help="Allow execution of specific task action (e.g., ws_noop)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=0,
        help="Maximum number of tasks to execute (0=disabled, max=1)",
    )
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=0,
        help="Task wait time after heartbeat (seconds, default 0=disabled)",
    )
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=float,
        default=1.0,
        help="Heartbeat send interval during listen mode (seconds, default 1.0)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Validate inputs
    if not args.server_url:
        logger.error("--server-url is required")
        return 2

    if not args.registration_code_env:
        logger.error("--registration-code-env is required")
        return 2

    # Validate task execution options
    if args.max_tasks > 1:
        logger.error("--max-tasks must be 0 or 1 (max 1 task)")
        return 2

    if args.allow_task_action and args.allow_task_action not in ("ws_noop", "safe_echo", "safe_desktop_capability", "safe_app_presence_known_paths", "safe_app_capability_matrix"):
        logger.error(
            "--allow-task-action must be 'ws_noop', 'safe_echo', 'safe_desktop_capability', 'safe_app_presence_known_paths', 'safe_app_capability_matrix', or empty (got %r)",
            args.allow_task_action
        )
        return 2

    if args.allow_task_action and args.max_tasks == 0:
        logger.error(
            "--allow-task-action requires --max-tasks > 0"
        )
        return 2

    # Validate listen mode options
    if args.listen_seconds > 0:
        if not args.allow_task_action:
            logger.error(
                "--listen-seconds requires --allow-task-action (ws_noop, safe_echo, safe_desktop_capability, safe_app_presence_known_paths, or safe_app_capability_matrix)"
            )
            return 2
        if args.allow_task_action not in ("ws_noop", "safe_echo", "safe_desktop_capability", "safe_app_presence_known_paths", "safe_app_capability_matrix"):
            logger.error(
                "--listen-seconds only works with --allow-task-action ws_noop, safe_echo, safe_desktop_capability, safe_app_presence_known_paths, or safe_app_capability_matrix"
            )
            return 2

    if args.heartbeat_interval_seconds <= 0:
        logger.error("--heartbeat-interval-seconds must be > 0")
        return 2

    # Load registration code from environment variable
    registration_code = os.environ.get(args.registration_code_env, "").strip()
    if not registration_code:
        logger.error(
            "Environment variable %r is not set or empty",
            args.registration_code_env
        )
        return 2

    # Import client
    try:
        from agent.local_agent_client import AgentConfig, LocalAgentClient
    except ImportError as e:
        logger.error("Failed to import required modules: %s", e)
        return 3

    # Step 1: Register agent with code (HTTP API)
    logger.info("Registering agent with registration code...")
    try:
        agent_id, device_token = _register_with_code(
            server_url=args.server_url,
            registration_code=registration_code,
            host=args.host,
            os_name=args.os_name,
            version=args.version,
        )
        logger.info("Agent registered: agent_id=%s", agent_id)
        # Do NOT log device_token
    except Exception as e:
        logger.error("Agent registration failed: %s", e)
        return 4

    # Step 2: Create client config
    logger.info("Setting up WebSocket client...")
    config = AgentConfig(
        server_base_url=args.server_url,
        agent_id=agent_id,
        device_token=device_token,
        heartbeat_interval=10.0,
        dry_run=False,  # Enable actual connection
    )

    # Step 3: Connect and run
    if args.allow_task_action:
        if args.listen_seconds > 0:
            logger.info(
                "Connecting to WebSocket (heartbeat_count=%d, "
                "allow_task_action=%s, max_tasks=%d, "
                "listen_seconds=%.1f, heartbeat_interval=%.1f)...",
                args.heartbeat_count, args.allow_task_action, args.max_tasks,
                args.listen_seconds, args.heartbeat_interval_seconds
            )
        else:
            logger.info(
                "Connecting to WebSocket (heartbeat_count=%d, "
                "allow_task_action=%s, max_tasks=%d)...",
                args.heartbeat_count, args.allow_task_action, args.max_tasks
            )
    else:
        logger.info(
            "Connecting to WebSocket (heartbeat_count=%d, no-task mode)...",
            args.heartbeat_count
        )
    client = LocalAgentClient(config)
    result = client.connect(
        heartbeat_count=args.heartbeat_count,
        allow_task_action=args.allow_task_action,
        max_tasks=args.max_tasks,
        listen_seconds=args.listen_seconds,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
    )

    # Log result (without sensitive values)
    status = result.get("status", "unknown")
    logger.info("Connection result: status=%s", status)

    if status == "ok":
        tasks_processed = result.get("tasks_processed", 0)
        no_task_received = result.get("no_task_received", False)
        logger.info(
            "WebSocket connection successful: "
            "agent_id=%s, heartbeat_count=%d, "
            "sent=%d, received=%d, tasks_processed=%d, no_task_received=%s",
            result.get("agent_id"),
            result.get("heartbeat_count"),
            result.get("sent"),
            result.get("received"),
            tasks_processed,
            no_task_received,
        )
        return 0
    else:
        error = result.get("error", "unknown error")
        logger.error("WebSocket connection failed: %s", error)
        return 6


if __name__ == "__main__":
    sys.exit(main())
