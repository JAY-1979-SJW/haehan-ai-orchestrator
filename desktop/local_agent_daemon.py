"""App-scoped local agent daemon for desktop runtime.

The desktop app owns this process only while the app is running. It does not
install a Windows service, does not register autostart, and does not pass raw
tokens on the command line. The agent process loads its device token from the
existing local token store.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import tray_runtime

logger = logging.getLogger(__name__)


@dataclass
class LocalAgentDaemonState:
    started: bool
    reason: str = ""
    pid: int = 0
    server_url: str = ""
    agent_id_masked: str = ""
    log_path: str = ""


def mask_agent_id(agent_id: str) -> str:
    if not agent_id or len(agent_id) < 10:
        return "??"
    return f"{agent_id[:6]}***{agent_id[-4:]}"


def build_agent_command(server_url: str) -> list[str]:
    """Return the local agent command without embedding tokens or secrets."""
    return [sys.executable, "-m", "local_agent.agent", "--run", "--server", server_url]


def build_agent_env(base: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = dict(base or os.environ)
    env["HAEHAN_AGENT_WS_ENABLED"] = "true"
    env.setdefault("HAEHAN_AGENT_POLL_SEC", "2")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def default_log_path(app_root: Path) -> Path:
    path = app_root / "logs" / "local_agent_daemon.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class LocalAgentDaemon:
    """Start and stop the local agent worker with the desktop app."""

    def __init__(
        self,
        *,
        app_root: Path,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self._app_root = app_root
        self._popen = popen
        self._proc: subprocess.Popen | None = None
        self._log_handle = None
        self.state = LocalAgentDaemonState(started=False, reason="not_started")

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, status: tray_runtime.RegistrationStatus) -> LocalAgentDaemonState:
        if self.running:
            return self.state
        if not status.registered:
            self.state = LocalAgentDaemonState(started=False, reason="not_registered")
            return self.state
        if not status.server_url or not status.agent_id:
            self.state = LocalAgentDaemonState(started=False, reason="config_incomplete")
            return self.state

        log_path = default_log_path(self._app_root)
        self._log_handle = open(log_path, "a", encoding="utf-8")
        command = build_agent_command(status.server_url)
        env = build_agent_env()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._proc = self._popen(
                command,
                cwd=str(self._app_root),
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001
            self._close_log()
            self.state = LocalAgentDaemonState(
                started=False,
                reason=f"start_failed:{type(exc).__name__}",
                server_url=status.server_url,
                agent_id_masked=mask_agent_id(status.agent_id),
                log_path=str(log_path),
            )
            logger.warning("local agent daemon start failed: %s", type(exc).__name__)
            return self.state

        self.state = LocalAgentDaemonState(
            started=True,
            reason="started",
            pid=int(getattr(self._proc, "pid", 0) or 0),
            server_url=status.server_url,
            agent_id_masked=mask_agent_id(status.agent_id),
            log_path=str(log_path),
        )
        logger.info(
            "local agent daemon started pid=%s agent=%s",
            self.state.pid,
            self.state.agent_id_masked,
        )
        return self.state

    def stop(self, timeout: float = 8.0) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                logger.warning("local agent daemon stop failed: %s", type(exc).__name__)
        self._close_log()
        if self.state.started:
            self.state = LocalAgentDaemonState(started=False, reason="stopped")

    def _close_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None


__all__ = [
    "LocalAgentDaemon",
    "LocalAgentDaemonState",
    "build_agent_command",
    "build_agent_env",
    "default_log_path",
    "mask_agent_id",
]
