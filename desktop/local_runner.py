"""Local browser task handler process manager (DESK-3).

Manages the lifecycle of the local browser task handler subprocess.
Connects ONLY to local mock runner — no production WebSocket connections.

States: starting / running / degraded / stopped / error
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Script that starts the local mock task runner (no production connections)
_DEFAULT_MOCK_RUNNER_SCRIPT = Path(__file__).parent.parent / "scripts" / "mock_task_server.py"


class LocalRunner:
    """Manages a single subprocess for the local browser task handler.

    Does NOT connect to production WebSocket or production API.
    Uses local mock only.
    """

    def __init__(
        self,
        runner_script: Optional[Path] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        self._script = runner_script or _DEFAULT_MOCK_RUNNER_SCRIPT
        self._python = python_executable or sys.executable
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._state = "stopped"

    # ------------------------------------------------------------------
    # Lifecycle

    def start(self) -> bool:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                logger.info("local runner already running (pid=%s)", self._process.pid)
                return True
            try:
                self._state = "starting"
                self._process = subprocess.Popen(
                    [self._python, str(self._script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._state = "running"
                logger.info("local runner started (pid=%s)", self._process.pid)
                return True
            except Exception as exc:
                self._state = "error"
                logger.error("local runner start failed: %s", exc)
                return False

    def stop(self) -> bool:
        with self._lock:
            if self._process is None:
                self._state = "stopped"
                return True
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                self._process = None
                self._state = "stopped"
                logger.info("local runner stopped")
                return True
            except Exception as exc:
                self._state = "error"
                logger.error("local runner stop failed: %s", exc)
                return False

    def restart(self) -> bool:
        self.stop()
        return self.start()

    # ------------------------------------------------------------------
    # Status

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def get_status(self) -> str:
        with self._lock:
            if self._process is None:
                return "stopped"
            rc = self._process.poll()
            if rc is None:
                return self._state if self._state == "starting" else "running"
            if rc == 0:
                return "stopped"
            return "error"

    def get_pid(self) -> Optional[int]:
        with self._lock:
            if self._process is None:
                return None
            return self._process.pid if self._process.poll() is None else None


__all__ = ["LocalRunner"]
