"""Client/launcher for the localhost CAD HTTP agent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from .config import ensure_cad_work_on_path


DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 8765
DEFAULT_AGENT_URL = f"http://{DEFAULT_AGENT_HOST}:{DEFAULT_AGENT_PORT}"
DEFAULT_REQUEST_TIMEOUT = 3


def cad_agent_health() -> dict[str, Any]:
    return _agent_get("/health", timeout_seconds=DEFAULT_REQUEST_TIMEOUT)


def _ping_local_http_agent(timeout_seconds: int = 5) -> dict[str, Any]:
    return _agent_get("/ping", timeout_seconds=timeout_seconds)


def cad_agent_connect(timeout_seconds: int = 20) -> dict[str, Any]:
    started = ensure_cad_agent_started()
    result = _agent_get("/connect", timeout_seconds=max(8, int(timeout_seconds)))
    if started.get("started"):
        result["agent_start"] = started
    return result


def cad_agent_status() -> dict[str, Any]:
    return _agent_get("/status", timeout_seconds=DEFAULT_REQUEST_TIMEOUT)


def cad_agent_active_document(timeout_seconds: int = 10) -> dict[str, Any]:
    return _agent_get("/active-document", timeout_seconds=max(3, int(timeout_seconds)))


def ensure_cad_agent_started() -> dict[str, Any]:
    health = cad_agent_health()
    if health.get("ok"):
        return {"ok": True, "started": False, "health": health}

    root = ensure_cad_work_on_path()
    log_dir = Path(os.environ.get("HAEHAN_CAD_AGENT_LOG_DIR", r"C:\tmp"))
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "cad_local_http_agent.out.log"
    stderr_path = log_dir / "cad_local_http_agent.err.log"

    cmd = [
        sys.executable,
        "-m",
        "local_worker_plugins.cad_app_controller.cad_local_http_agent",
        "--host",
        DEFAULT_AGENT_HOST,
        "--port",
        str(DEFAULT_AGENT_PORT),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stdout = stdout_path.open("ab")
    stderr = stderr_path.open("ab")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()

    deadline = time.monotonic() + 5
    last_health = health
    while time.monotonic() < deadline:
        time.sleep(0.25)
        last_health = cad_agent_health()
        if last_health.get("ok"):
            return {
                "ok": True,
                "started": True,
                "pid": process.pid,
                "health": last_health,
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
            }

    return {
        "ok": False,
        "started": True,
        "pid": process.pid,
        "health": last_health,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "error": "CAD agent did not answer /health within 5s.",
    }


def _agent_get(path: str, timeout_seconds: int) -> dict[str, Any]:
    url = DEFAULT_AGENT_URL + path
    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            payload["agent_url"] = DEFAULT_AGENT_URL
            payload["transport"] = "local_http_agent"
            return payload
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "AGENT_UNAVAILABLE",
            "agent_url": DEFAULT_AGENT_URL,
            "transport": "local_http_agent",
            "error": repr(exc),
        }
