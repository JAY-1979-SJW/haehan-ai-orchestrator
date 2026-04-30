"""Local browser task handler process manager (DESK-3, hardened in P1-FIX).

Manages the lifecycle of the local browser task handler subprocess.
Connects ONLY to local mock runner — no production WebSocket connections.

States: starting / running / degraded / stopped / error

P1-FIX hardening:
- Popen 직후 짧은 검증 (poll()) — 즉시 죽으면 state="error"
- stdout/stderr → 로그 파일 redirect (PIPE buffer block 방지)
- secret 노출 방지: 로그 파일 위치는 local logs 디렉터리
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Script that starts the local mock task runner (no production connections)
_DEFAULT_MOCK_RUNNER_SCRIPT = Path(__file__).parent.parent / "scripts" / "mock_task_server.py"

# Default location for runner logs (NOT subprocess.PIPE — avoids buffer block)
_DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"

# Time to wait after spawn before verifying process is still alive (seconds)
_START_VERIFY_DELAY = 0.2


class LocalRunner:
    """Manages a single subprocess for the local browser task handler.

    Does NOT connect to production WebSocket or production API.
    Uses local mock only. Stdout/stderr redirected to local log files.
    """

    def __init__(
        self,
        runner_script: Optional[Path] = None,
        python_executable: Optional[str] = None,
        log_dir: Optional[Path] = None,
        start_verify_delay: float = _START_VERIFY_DELAY,
    ) -> None:
        self._script = runner_script or _DEFAULT_MOCK_RUNNER_SCRIPT
        self._python = python_executable or sys.executable
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._start_verify_delay = start_verify_delay
        self._process: Optional[subprocess.Popen] = None
        self._stdout_fp = None
        self._stderr_fp = None
        self._lock = threading.Lock()
        self._state = "stopped"
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Log file management

    def _open_log_files(self) -> tuple:
        """Open per-run stdout/stderr log files. Returns (stdout_fp, stderr_fp)."""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stdout_path = self._log_dir / f"local_runner_{ts}.stdout.log"
        stderr_path = self._log_dir / f"local_runner_{ts}.stderr.log"
        # Append mode — never overwrite existing operator logs
        return (
            open(stdout_path, "ab", buffering=0),
            open(stderr_path, "ab", buffering=0),
        )

    def _close_log_files(self) -> None:
        for fp in (self._stdout_fp, self._stderr_fp):
            if fp is not None:
                try:
                    fp.close()
                except Exception:
                    pass
        self._stdout_fp = None
        self._stderr_fp = None

    # ------------------------------------------------------------------
    # Lifecycle

    def start(self) -> bool:
        """Start subprocess + verify it survived initial spawn.

        Returns True only if process is alive after _start_verify_delay.
        Returns False (with state=error) if process exited immediately.
        """
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                logger.info("local runner already running (pid=%s)", self._process.pid)
                return True

            self._last_error = None
            self._state = "starting"

            # Open per-run log files (NOT PIPE — avoids buffer block)
            try:
                self._stdout_fp, self._stderr_fp = self._open_log_files()
            except OSError as exc:
                self._state = "error"
                self._last_error = f"failed to open log files: {exc}"
                logger.error(self._last_error)
                return False

            # Spawn process
            try:
                self._process = subprocess.Popen(
                    [self._python, str(self._script)],
                    stdout=self._stdout_fp,
                    stderr=self._stderr_fp,
                    stdin=subprocess.DEVNULL,
                )
            except Exception as exc:
                self._state = "error"
                self._last_error = f"spawn failed: {exc}"
                logger.error(self._last_error)
                self._close_log_files()
                self._process = None
                return False

        # Verify outside lock (sleep doesn't need to block other readers)
        time.sleep(self._start_verify_delay)

        with self._lock:
            if self._process is None:
                # Stopped concurrently
                return False

            rc = self._process.poll()
            if rc is not None:
                # Process died immediately
                self._state = "error"
                self._last_error = f"process exited immediately (rc={rc})"
                logger.error(self._last_error)
                self._close_log_files()
                self._process = None
                return False

            self._state = "running"
            logger.info("local runner started (pid=%s)", self._process.pid)
            return True

    def stop(self) -> bool:
        with self._lock:
            if self._process is None:
                self._state = "stopped"
                self._close_log_files()
                return True
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=2)
                self._process = None
                self._close_log_files()
                self._state = "stopped"
                logger.info("local runner stopped")
                return True
            except Exception as exc:
                self._state = "error"
                self._last_error = f"stop failed: {exc}"
                logger.error(self._last_error)
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
                # If we ever transitioned to error, preserve it
                if self._state == "error":
                    return "error"
                return "stopped"
            rc = self._process.poll()
            if rc is None:
                return self._state if self._state == "starting" else "running"
            if rc == 0:
                return "stopped"
            self._state = "error"
            return "error"

    def get_pid(self) -> Optional[int]:
        with self._lock:
            if self._process is None:
                return None
            return self._process.pid if self._process.poll() is None else None

    def get_last_error(self) -> Optional[str]:
        """Return last error summary (no secrets)."""
        with self._lock:
            return self._last_error


__all__ = ["LocalRunner"]
