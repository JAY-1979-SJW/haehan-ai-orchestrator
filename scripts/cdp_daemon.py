"""AI 전용 CDP 데몬 — Playwright 브라우저 상시 실행.

용도:
  - CDP 서버를 상시 실행
  - AI 전용 브라우저 세션 유지
  - 여러 명령이 동일 세션에서 실행

실행:
  python scripts/cdp_daemon.py start       # 데몬 시작
  python scripts/cdp_daemon.py stop        # 데몬 정지
  python scripts/cdp_daemon.py status      # 상태 확인
  python scripts/cdp_daemon.py logs        # 로그 확인
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.local_agent.browser.browser_session import get_session_dir

# ── 설정 ──

DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"
DAEMON_LOG_FILE = ROOT / "data" / "logs" / "cdp_daemon.log"
PROFILE_NAME = "ai_assistant"
CDP_TIMEOUT = 300  # 5분

_log_file = DAEMON_LOG_FILE
_log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cdp_daemon")


# ── 상태 관리 ──

@dataclass
class DaemonState:
    """데몬 상태."""
    running: bool = False
    pid: int = 0
    started_at: str = ""
    last_heartbeat: str = ""
    browser_context: str = ""  # "active" / "inactive"
    total_commands: int = 0
    last_error: str = ""


def _save_state(state: DaemonState) -> None:
    """상태 저장."""
    DAEMON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "running": state.running,
        "pid": state.pid,
        "started_at": state.started_at,
        "last_heartbeat": state.last_heartbeat,
        "browser_context": state.browser_context,
        "total_commands": state.total_commands,
        "last_error": state.last_error,
    }
    DAEMON_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_state() -> DaemonState:
    """상태 로드."""
    if not DAEMON_STATE_FILE.exists():
        return DaemonState()
    try:
        data = json.loads(DAEMON_STATE_FILE.read_text(encoding="utf-8"))
        return DaemonState(**data)
    except Exception:
        return DaemonState()


# ── CDP 브라우저 관리 ──

class CDPBrowser:
    """AI 전용 CDP 브라우저 세션."""

    def __init__(self, profile_name: str = "ai_assistant"):
        self.profile_name = profile_name
        self.session_dir = get_session_dir(profile_name)
        self.context: Any = None
        self.browser: Any = None
        self.playwright: Any = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """브라우저 시작."""
        with self._lock:
            try:
                from playwright.sync_api import sync_playwright

                log.info("[CDP] 브라우저 시작 중... (프로필: %s)", self.profile_name)

                self.playwright = sync_playwright().start()
                storage_state_path = self.session_dir / "state.json"

                # storage_state 로드
                storage_state_kwarg = {}
                if storage_state_path.is_file():
                    storage_state_kwarg["storage_state"] = str(storage_state_path)
                    log.info("[CDP] 저장된 세션 복원: %s", storage_state_path.name)

                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=True,  # 백그라운드
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",  # 자동화 감지 숨김
                    ],
                    **storage_state_kwarg,
                )
                log.info("✓ CDP 브라우저 시작 완료")
                return True

            except Exception as e:
                log.error("✗ 브라우저 시작 실패: %s", e, exc_info=True)
                return False

    def stop(self) -> bool:
        """브라우저 정지 + 세션 저장."""
        with self._lock:
            try:
                if self.context:
                    log.info("[CDP] 세션 저장 중...")
                    storage_state_path = self.session_dir / "state.json"
                    self.context.storage_state(path=str(storage_state_path))
                    log.info("✓ 세션 저장: %s", storage_state_path.name)

                    self.context.close()
                    log.info("[CDP] 컨텍스트 종료")

                if self.playwright:
                    self.playwright.stop()
                    log.info("[CDP] Playwright 종료")

                return True
            except Exception as e:
                log.error("✗ 브라우저 정지 실패: %s", e, exc_info=True)
                return False

    def new_page(self) -> Any:
        """새 페이지 생성."""
        if not self.context:
            log.error("컨텍스트가 없습니다")
            return None
        return self.context.new_page()

    def goto(self, url: str) -> bool:
        """URL 이동."""
        try:
            page = self.new_page()
            if not page:
                return False
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            return True
        except Exception as e:
            log.error("페이지 이동 실패: %s", e)
            return False


# ── 메인 루프 ──

_browser: CDPBrowser | None = None
_state = DaemonState()
_stop_event = threading.Event()


def heartbeat_loop():
    """주기적 heartbeat."""
    while not _stop_event.is_set():
        try:
            _state.last_heartbeat = datetime.utcnow().isoformat()
            _state.browser_context = "active" if _browser and _browser.context else "inactive"
            _save_state(_state)

            log.debug(
                "[HEARTBEAT] pid=%d running=%s browser=%s commands=%d",
                os.getpid(),
                _state.running,
                _state.browser_context,
                _state.total_commands,
            )

            _stop_event.wait(timeout=10)  # 10초 주기
        except Exception as e:
            log.error("Heartbeat 오류: %s", e)


def signal_handler(signum: int, frame: Any) -> None:
    """신호 처리 (SIGTERM, SIGINT)."""
    log.info("신호 수신: %d, 종료 중...", signum)
    _stop_event.set()


def run_daemon() -> None:
    """데몬 메인 루프."""
    global _browser, _state

    log.info("=" * 60)
    log.info("  AI CDP 데몬 시작")
    log.info("  PID: %d", os.getpid())
    log.info("  프로필: %s", PROFILE_NAME)
    log.info("=" * 60)

    # 신호 등록
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 상태 초기화
    _state = DaemonState(
        running=True,
        pid=os.getpid(),
        started_at=datetime.utcnow().isoformat(),
        browser_context="starting",
    )
    _save_state(_state)

    # 브라우저 시작
    _browser = CDPBrowser(profile_name=PROFILE_NAME)
    if not _browser.start():
        log.error("브라우저 시작 실패")
        _state.running = False
        _state.last_error = "browser_start_failed"
        _save_state(_state)
        return

    _state.browser_context = "active"
    _save_state(_state)

    # Heartbeat 스레드
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    log.info("✓ 데몬 준비 완료. 명령 대기 중...")

    try:
        # 메인 루프 — 종료 신호 대기
        while not _stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("키보드 인터럽트 수신")
    finally:
        log.info("데몬 종료 중...")
        if _browser:
            _browser.stop()

        _state.running = False
        _state.browser_context = "inactive"
        _save_state(_state)

        log.info("=" * 60)
        log.info("  데몬 종료")
        log.info("=" * 60)


# ── CLI 명령 ──

def cmd_start() -> None:
    """데몬 시작."""
    state = _load_state()
    if state.running:
        print(f"✓ 데몬이 이미 실행 중입니다 (PID: {state.pid})")
        return

    print("데몬 시작 중...")
    run_daemon()


def cmd_stop() -> None:
    """데몬 정지."""
    state = _load_state()
    if not state.running:
        print("데몬이 실행 중이지 않습니다")
        return

    print(f"데몬 정지 중... (PID: {state.pid})")
    try:
        os.kill(state.pid, signal.SIGTERM)
        time.sleep(2)
        print("✓ 데몬 정지 완료")
    except ProcessLookupError:
        print("⚠  프로세스를 찾을 수 없습니다")


def cmd_status() -> None:
    """상태 확인."""
    state = _load_state()
    print("=" * 60)
    print("CDP 데몬 상태")
    print("=" * 60)
    print(f"실행: {'✓ 예' if state.running else '✗ 아니오'}")
    if state.running:
        print(f"PID: {state.pid}")
        print(f"시작: {state.started_at}")
        print(f"마지막 하트비트: {state.last_heartbeat}")
        print(f"브라우저: {state.browser_context}")
        print(f"명령 실행: {state.total_commands}회")
        if state.last_error:
            print(f"마지막 에러: {state.last_error}")


def cmd_logs() -> None:
    """로그 확인."""
    if not DAEMON_LOG_FILE.exists():
        print("로그 파일이 없습니다")
        return

    lines = DAEMON_LOG_FILE.read_text(encoding="utf-8").split("\n")
    # 최근 30줄만 출력
    for line in lines[-30:]:
        if line.strip():
            print(line)


def main() -> None:
    """메인."""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    match cmd:
        case "start":
            cmd_start()
        case "stop":
            cmd_stop()
        case "status":
            cmd_status()
        case "logs":
            cmd_logs()
        case _:
            print(f"알 수 없는 명령: {cmd}")
            print(__doc__)


if __name__ == "__main__":
    main()
