"""AI 전용 CDP 데몬 — Chrome을 CDP 포트와 함께 상시 실행.

구조:
  데몬이 Chrome을 --remote-debugging-port=9222 로 실행하고 유지.
  Chrome이 죽으면 자동 재시작.
  클라이언트는 이 포트로 연결해 같은 브라우저 인스턴스에서 명령 실행.

실행:
  python scripts/cdp_daemon.py start       # 백그라운드 데몬 시작
  python scripts/cdp_daemon.py stop        # 데몬 정지
  python scripts/cdp_daemon.py restart     # 재시작
  python scripts/cdp_daemon.py status      # 상태 확인
  python scripts/cdp_daemon.py logs        # 로그 확인
  python scripts/cdp_daemon.py install     # Windows 로그인 시 자동 시작 등록
  python scripts/cdp_daemon.py uninstall   # 자동 시작 해제
  python scripts/cdp_daemon.py _run        # 내부 전용 (데몬 본체 직접 실행)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.config import CDP_PORT  # noqa: E402

# ── 설정 ─────────────────────────────────────────────────────────────
DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"
DAEMON_LOG_FILE   = ROOT / "data" / "logs" / "cdp_daemon.log"
PROFILE_DIR       = ROOT / "data" / "cdp_profile" / "ai_chrome"
BROWSER_TYPE      = os.environ.get("CDP_BROWSER", "auto")
TASK_NAME         = "HaehanCdpDaemon"          # Task Scheduler 작업명
MAX_RESTART       = int(os.environ.get("CDP_MAX_RESTART", "10"))  # 최대 재시작 횟수

DAEMON_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(DAEMON_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cdp_daemon")


# ── 상태 ─────────────────────────────────────────────────────────────
@dataclass
class DaemonState:
    running: bool        = False
    pid: int             = 0
    chrome_pid: int      = 0
    cdp_port: int        = CDP_PORT
    browser_context: str = "inactive"   # active / inactive
    started_at: str      = ""
    last_heartbeat: str  = ""
    last_error: str      = ""
    restart_count: int   = 0


def _save_state(s: DaemonState) -> None:
    DAEMON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_STATE_FILE.write_text(
        json.dumps(s.__dict__, indent=2), encoding="utf-8"
    )


def _load_state() -> DaemonState:
    if not DAEMON_STATE_FILE.exists():
        return DaemonState()
    try:
        data = json.loads(DAEMON_STATE_FILE.read_text(encoding="utf-8"))
        return DaemonState(**{k: v for k, v in data.items() if k in DaemonState.__dataclass_fields__})
    except Exception:
        return DaemonState()


# ── 브라우저 탐색 & 실행 ─────────────────────────────────────────────
def _find_browser(browser_type: str = "auto") -> tuple[str, str]:
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]

    def _find(candidates: list[str]) -> str | None:
        return next((p for p in candidates if Path(p).exists()), None)

    if browser_type == "chrome":
        exe = _find(chrome_candidates)
        if not exe:
            raise FileNotFoundError("Chrome을 찾을 수 없습니다.")
        return exe, "chrome"
    elif browser_type == "edge":
        exe = _find(edge_candidates)
        if not exe:
            raise FileNotFoundError("Edge를 찾을 수 없습니다.")
        return exe, "edge"
    else:
        exe = _find(chrome_candidates)
        if exe:
            return exe, "chrome"
        exe = _find(edge_candidates)
        if exe:
            return exe, "edge"
        raise FileNotFoundError("Chrome 또는 Edge를 찾을 수 없습니다.")


def _launch_chrome(port: int = CDP_PORT) -> subprocess.Popen:
    exe, kind = _find_browser(BROWSER_TYPE)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--start-maximized",
    ]
    log.info("[BROWSER] 종류=%s port=%d profile=%s", kind, port, PROFILE_DIR)
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("[BROWSER] PID=%d", proc.pid)
    return proc


def _is_cdp_ready(port: int = CDP_PORT, timeout: int = 15) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


# ── 데몬 본체 ─────────────────────────────────────────────────────────
_stop_event = threading.Event()
_state = DaemonState()
_chrome_proc: subprocess.Popen | None = None
_restart_lock = threading.Lock()


def _restart_chrome() -> None:
    """Chrome 재시작 (락으로 중복 방지)."""
    global _chrome_proc
    with _restart_lock:
        if _state.restart_count >= MAX_RESTART:
            log.error("최대 재시작 횟수(%d) 초과 — 데몬 종료", MAX_RESTART)
            _stop_event.set()
            return

        _state.restart_count += 1
        log.warning("[RESTART] Chrome 재시작 시도 #%d", _state.restart_count)
        _state.browser_context = "inactive"
        _state.last_error = f"chrome_died (restart #{_state.restart_count})"
        _save_state(_state)

        # 기존 프로세스 정리
        if _chrome_proc and _chrome_proc.poll() is None:
            try:
                _chrome_proc.terminate()
                _chrome_proc.wait(timeout=5)
            except Exception:
                pass

        time.sleep(2)

        try:
            _chrome_proc = _launch_chrome(CDP_PORT)
            _state.chrome_pid = _chrome_proc.pid
            _save_state(_state)

            if _is_cdp_ready(CDP_PORT):
                _state.browser_context = "active"
                _state.last_error = ""
                log.info("[RESTART] Chrome 재시작 성공 PID=%d", _chrome_proc.pid)
            else:
                log.error("[RESTART] CDP 포트 응답 없음")
                _state.last_error = "cdp_port_timeout_after_restart"
            _save_state(_state)
        except Exception as e:
            log.error("[RESTART] 실패: %s", e)
            _state.last_error = str(e)
            _save_state(_state)


def _heartbeat_loop() -> None:
    while not _stop_event.is_set():
        try:
            _state.last_heartbeat = datetime.now(timezone.utc).isoformat()

            # Chrome 프로세스 생존 확인 → 죽었으면 자동 재시작
            if _chrome_proc and _chrome_proc.poll() is not None:
                log.warning("[HEARTBEAT] Chrome 프로세스 종료 감지 → 자동 재시작")
                threading.Thread(target=_restart_chrome, daemon=True).start()

            _save_state(_state)
        except Exception as e:
            log.error("[HEARTBEAT] 오류: %s", e)
        _stop_event.wait(timeout=10)


def _signal_handler(signum: int, frame: Any) -> None:
    log.info("신호 수신: %d → 종료", signum)
    _stop_event.set()


def run_daemon() -> None:
    global _chrome_proc, _state

    log.info("=" * 60)
    log.info("  AI CDP 데몬 시작 (상시 실행 모드)")
    log.info("  PID: %d  CDP 포트: %d", os.getpid(), CDP_PORT)
    log.info("  프로필: %s", PROFILE_DIR)
    log.info("  최대 재시작: %d회", MAX_RESTART)
    log.info("=" * 60)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    _state.__init__(
        running=True,
        pid=os.getpid(),
        cdp_port=CDP_PORT,
        browser_context="inactive",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _save_state(_state)

    # Chrome 실행
    try:
        _chrome_proc = _launch_chrome(CDP_PORT)
        _state.chrome_pid = _chrome_proc.pid
        _save_state(_state)
    except Exception as e:
        log.error("Chrome 실행 실패: %s", e)
        _state.running = False
        _state.last_error = str(e)
        _save_state(_state)
        return

    # CDP 준비 대기
    log.info("[CDP] 포트 %d 응답 대기...", CDP_PORT)
    if not _is_cdp_ready(CDP_PORT):
        log.error("CDP 포트 응답 없음 — 종료")
        _state.running = False
        _state.last_error = "cdp_port_timeout"
        _save_state(_state)
        _chrome_proc.terminate()
        return

    _state.browser_context = "active"
    _save_state(_state)
    log.info("✓ CDP 포트 %d 준비 완료", CDP_PORT)

    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    log.info("✓ 데몬 상시 대기 중...")
    try:
        while not _stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("데몬 종료 중...")
        if _chrome_proc and _chrome_proc.poll() is None:
            _chrome_proc.terminate()
            log.info("[CHROME] 종료 (PID=%d)", _chrome_proc.pid)
        _state.running = False
        _state.chrome_pid = 0
        _state.browser_context = "inactive"
        _save_state(_state)
        log.info("데몬 종료 완료")


# ── CLI 명령 ─────────────────────────────────────────────────────────
def cmd_start() -> None:
    import urllib.request

    # 이미 CDP 포트 응답 중이면 스킵
    try:
        urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
        print(f"✓ CDP 데몬 이미 실행 중 (포트={CDP_PORT})")
        return
    except Exception:
        pass

    script = Path(__file__).resolve()
    if sys.platform == "win32":
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        proc = subprocess.Popen(
            [str(pythonw), str(script), "_run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        proc = subprocess.Popen(
            [sys.executable, str(script), "_run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    print(f"✓ CDP 데몬 백그라운드 시작 (PID={proc.pid})")

    # CDP 응답 대기
    print(f"  CDP 포트 {CDP_PORT} 응답 대기 중...", end="", flush=True)
    if _is_cdp_ready(CDP_PORT, timeout=20):
        print(" ✓")
    else:
        print(" ⚠ (시간 초과 — 로그 확인 필요)")


def cmd_stop() -> None:
    state = _load_state()

    stopped = False
    # Chrome 종료
    if state.chrome_pid:
        try:
            os.kill(state.chrome_pid, signal.SIGTERM)
            print(f"✓ Chrome 종료 (PID={state.chrome_pid})")
            stopped = True
        except Exception as e:
            print(f"⚠  Chrome 종료 실패: {e}")

    # 데몬 프로세스 종료
    if state.pid and state.pid != os.getpid():
        try:
            os.kill(state.pid, signal.SIGTERM)
            print(f"✓ 데몬 종료 (PID={state.pid})")
            stopped = True
        except Exception as e:
            print(f"⚠  데몬 종료 실패: {e}")

    state.running = False
    state.chrome_pid = 0
    state.browser_context = "inactive"
    _save_state(state)

    if not stopped:
        print("실행 중인 데몬 없음")
    else:
        print("✓ 데몬 정지 완료")


def cmd_restart() -> None:
    print("데몬 재시작 중...")
    cmd_stop()
    time.sleep(2)
    cmd_start()


def cmd_status() -> None:
    import urllib.request
    state = _load_state()

    print("=" * 60)
    print("CDP 데몬 상태")
    print("=" * 60)
    print(f"실행:         {'✓ 예' if state.running else '✗ 아니오'}")

    if state.running:
        try:
            urllib.request.urlopen(f"http://localhost:{state.cdp_port}/json/version", timeout=2)
            cdp_ok = "✓ 응답 중"
        except Exception:
            cdp_ok = "✗ 응답 없음"

        print(f"데몬 PID:     {state.pid}")
        print(f"Chrome PID:   {state.chrome_pid}")
        print(f"CDP 포트:     {state.cdp_port}  ({cdp_ok})")
        print(f"브라우저:     {state.browser_context}")
        print(f"재시작 횟수:  {state.restart_count}")
        print(f"시작:         {state.started_at}")
        print(f"하트비트:     {state.last_heartbeat}")
        if state.last_error:
            print(f"마지막 오류: {state.last_error}")

    # 시작 프로그램 등록 여부 확인
    vbs_path  = _startup_folder() / f"{TASK_NAME}.vbs"
    installed = vbs_path.exists()
    print(f"자동시작 등록: {'✓ 등록됨' if installed else '✗ 미등록'}")


def _startup_folder() -> Path:
    """현재 사용자 시작 프로그램 폴더 경로 (Windows 전용)."""
    if sys.platform != "win32":
        raise RuntimeError("시작 프로그램 등록은 Windows 전용입니다")
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def cmd_install() -> None:
    """시작 프로그램 폴더에 VBS 래퍼 등록 — 로그인 시 자동 시작 (Windows 전용)."""
    if sys.platform != "win32":
        print("✗ install 명령은 Windows 전용입니다")
        print("  Linux에서는 systemd 서비스로 등록하세요:")
        print(f"  python {Path(__file__).name} _run  (ExecStart에 지정)")
        return

    script  = Path(__file__).resolve()
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)

    startup_dir = _startup_folder()
    vbs_path    = startup_dir / f"{TASK_NAME}.vbs"

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """{pythonw}"" ""{script}"" _run", 0, False
'''
    startup_dir.mkdir(parents=True, exist_ok=True)
    vbs_path.write_text(vbs_content, encoding="utf-8")

    print(f"✓ 시작 프로그램 등록 완료")
    print(f"  파일: {vbs_path}")
    print(f"  실행: {pythonw} {script} _run")
    print("  트리거: Windows 로그인 시 자동 시작")


def cmd_uninstall() -> None:
    """시작 프로그램 폴더에서 제거 (Windows 전용)."""
    if sys.platform != "win32":
        print("✗ uninstall 명령은 Windows 전용입니다")
        return
    vbs_path = _startup_folder() / f"{TASK_NAME}.vbs"
    if vbs_path.exists():
        vbs_path.unlink()
        print(f"✓ 시작 프로그램 등록 해제: {vbs_path}")
    else:
        print("⚠  등록된 항목 없음")


def cmd_logs() -> None:
    if not DAEMON_LOG_FILE.exists():
        print("로그 없음")
        return
    lines = DAEMON_LOG_FILE.read_text(encoding="utf-8").splitlines()
    for line in lines[-40:]:
        if line.strip():
            print(line)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    match sys.argv[1]:
        case "start":     cmd_start()
        case "stop":      cmd_stop()
        case "restart":   cmd_restart()
        case "status":    cmd_status()
        case "install":   cmd_install()
        case "uninstall": cmd_uninstall()
        case "logs":      cmd_logs()
        case "_run":      run_daemon()   # 내부 전용
        case _:
            print(f"알 수 없는 명령: {sys.argv[1]}")
            print(__doc__)


if __name__ == "__main__":
    main()
