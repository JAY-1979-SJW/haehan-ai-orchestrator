# -*- coding: utf-8 -*-
"""CAD bridge subprocess lifecycle manager — desktop hub side.

CAD-DESKTOP-HUB-CAD-BRIDGE-LIFECYCLE-01.

LocalRunner 패턴 복제 + CAD bridge 전용 차이점:
- 실행 명령: `python -m uvicorn local_bridge.server:app
  --host {host} --port {port} --log-level info`
- cwd 필수: `config.cad_repo_path` (CAD repo 루트 — local_bridge 모듈 import)
- cad_repo_path 미설정 → start 실패 + state=error + last_error 기록
- start_verify_delay 기본 1.0s (uvicorn listen 까지 여유)

안전 정책:
- 자기가 Popen 한 _process 만 terminate. 외부 PID 입력 0건.
- desktop.local_server / 다른 외부 프로세스에 어떤 영향도 주지 않음.
- 8765 사용 금지 (CadBridgeConfig 가 거부). 8001 금지.
- local_bridge / app.backend / app.frontend / mcp_server 모듈 import 0건.
- AutoCAD bridge COM / native Windows COM / DB write 0건.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .cad_bridge_registry import (
    CadBridgeConfig,
    DESKTOP_HUB_PORT,
    FORBIDDEN_CAD_BRIDGE_PORTS,
    load_default_config,
)

logger = logging.getLogger(__name__)

# Default log dir — desktop logs (LocalRunner 와 동일 위치 가족)
_DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"

# uvicorn listen 까지 ~0.5s 소요 — 여유롭게 1.0s
_DEFAULT_START_VERIFY_DELAY = 1.0


# ──────────────────────────────────────────────
# 상태 라벨 (LocalRunner 와 동일 어휘)
# ──────────────────────────────────────────────

STATE_STOPPED = "stopped"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_ERROR = "error"


# ──────────────────────────────────────────────
# CadBridgeRunner
# ──────────────────────────────────────────────

class CadBridgeRunner:
    """CAD local_bridge subprocess 관리.

    - start(): cad_repo_path / port 검증 → Popen([uvicorn ...], cwd=cad_repo_path)
    - stop(): terminate → wait(5s) → kill → wait(2s) (자기 process 만)
    - restart(): stop + start
    - is_running() / get_status() / get_pid() / get_last_error() — thread-safe

    외부 PID 인자 0건. native OS process kill API 호출 0건.
    """

    def __init__(
        self,
        config: Optional[CadBridgeConfig] = None,
        python_executable: Optional[str] = None,
        log_dir: Optional[Path] = None,
        start_verify_delay: float = _DEFAULT_START_VERIFY_DELAY,
    ) -> None:
        self._config = config or load_default_config()
        self._python = python_executable or sys.executable
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._start_verify_delay = start_verify_delay
        self._process: Optional[subprocess.Popen] = None
        self._stdout_fp = None
        self._stderr_fp = None
        self._lock = threading.Lock()
        self._state: str = STATE_STOPPED
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # config / command

    @property
    def config(self) -> CadBridgeConfig:
        return self._config

    def set_config(self, config: CadBridgeConfig) -> None:
        with self._lock:
            self._config = config

    def build_command(self) -> List[str]:
        """uvicorn 실행 명령 list 반환 — 실제 Popen 호출 없이 검증 가능."""
        return [
            self._python, "-m", "uvicorn",
            "local_bridge.server:app",
            "--host", self._config.host,
            "--port", str(self._config.port),
            "--log-level", "info",
        ]

    def _validate_before_start(self) -> Optional[str]:
        """start 전 사전 검증. 실패 사유 문자열 반환. 통과 시 None."""
        if self._config.port in FORBIDDEN_CAD_BRIDGE_PORTS:
            return f"forbidden port: {self._config.port}"
        if self._config.port == DESKTOP_HUB_PORT:
            return (
                f"cannot use desktop hub port {DESKTOP_HUB_PORT} for CAD bridge"
            )
        if not self._config.cad_repo_path:
            return "cad_repo_path required (set CAD_REPO_PATH env)"
        cwd = Path(self._config.cad_repo_path)
        if not cwd.exists():
            return f"cad_repo_path does not exist: {cwd}"
        if not cwd.is_dir():
            return f"cad_repo_path is not a directory: {cwd}"
        # local_bridge 패키지 존재만 확인 (import 하지 않음 — 본 정책상 금지)
        if not (cwd / "local_bridge" / "server.py").exists():
            return (
                "cad_repo_path does not look like CAD repo "
                "(missing local_bridge/server.py)"
            )
        return None

    # ------------------------------------------------------------------
    # log files

    def _open_log_files(self) -> tuple:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stdout_path = self._log_dir / f"cad_bridge_{ts}.stdout.log"
        stderr_path = self._log_dir / f"cad_bridge_{ts}.stderr.log"
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
        """Spawn subprocess + verify it survived initial spawn."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                logger.info(
                    "cad_bridge_runner already running (pid=%s)",
                    self._process.pid,
                )
                return True

            err = self._validate_before_start()
            if err:
                self._state = STATE_ERROR
                self._last_error = err
                logger.error("cad_bridge_runner start blocked: %s", err)
                return False

            self._last_error = None
            self._state = STATE_STARTING

            try:
                self._stdout_fp, self._stderr_fp = self._open_log_files()
            except OSError as exc:
                self._state = STATE_ERROR
                self._last_error = f"failed to open log files: {exc}"
                logger.error(self._last_error)
                return False

            cmd = self.build_command()
            cwd = self._config.cad_repo_path

            try:
                self._process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdout=self._stdout_fp,
                    stderr=self._stderr_fp,
                    stdin=subprocess.DEVNULL,
                )
            except Exception as exc:
                self._state = STATE_ERROR
                self._last_error = f"spawn failed: {exc}"
                logger.error(self._last_error)
                self._close_log_files()
                self._process = None
                return False

        time.sleep(self._start_verify_delay)

        with self._lock:
            if self._process is None:
                return False
            rc = self._process.poll()
            if rc is not None:
                self._state = STATE_ERROR
                self._last_error = f"process exited immediately (rc={rc})"
                logger.error(self._last_error)
                self._close_log_files()
                self._process = None
                return False
            self._state = STATE_RUNNING
            logger.info(
                "cad_bridge_runner started (pid=%s, port=%s)",
                self._process.pid, self._config.port,
            )
            return True

    def stop(self) -> bool:
        """자기가 Popen 한 child 만 terminate. 외부 PID 0건."""
        with self._lock:
            if self._process is None:
                self._state = STATE_STOPPED
                self._close_log_files()
                return True
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # 자기 Popen handle 의 kill — 외부 PID 아님
                        self._process.kill()
                        self._process.wait(timeout=2)
                self._process = None
                self._close_log_files()
                self._state = STATE_STOPPED
                logger.info("cad_bridge_runner stopped")
                return True
            except Exception as exc:
                self._state = STATE_ERROR
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
                if self._state == STATE_ERROR:
                    return STATE_ERROR
                return STATE_STOPPED
            rc = self._process.poll()
            if rc is None:
                return (
                    self._state if self._state == STATE_STARTING
                    else STATE_RUNNING
                )
            if rc == 0:
                return STATE_STOPPED
            self._state = STATE_ERROR
            return STATE_ERROR

    def get_pid(self) -> Optional[int]:
        with self._lock:
            if self._process is None:
                return None
            return self._process.pid if self._process.poll() is None else None

    def get_last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def snapshot(self) -> dict:
        """현재 runner 상태 dict — route 응답용."""
        return {
            "state": self.get_status(),
            "pid": self.get_pid(),
            "port": self._config.port,
            "host": self._config.host,
            "cadRepoPath": self._config.cad_repo_path,
            "lastError": self.get_last_error(),
        }


__all__ = [
    "CadBridgeRunner",
    "STATE_STOPPED",
    "STATE_STARTING",
    "STATE_RUNNING",
    "STATE_ERROR",
]
