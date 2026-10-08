"""AI 전용 CDP 데몬 — Chrome을 CDP 포트와 함께 상시 실행.

구조:
  데몬이 Chrome을 --remote-debugging-port=9222 로 실행하고 유지.
  Chrome이 죽으면 자동 재시작.
  클라이언트는 이 포트로 연결해 같은 브라우저 인스턴스에서 명령 실행.

실행:
  python scripts/browser/cdp/cdp_daemon.py start       # 백그라운드 데몬 시작
  python scripts/browser/cdp/cdp_daemon.py stop        # 데몬 정지
  python scripts/browser/cdp/cdp_daemon.py restart     # 재시작
  python scripts/browser/cdp/cdp_daemon.py status      # 상태 확인
  python scripts/browser/cdp/cdp_daemon.py logs        # 로그 확인
  python scripts/browser/cdp/cdp_daemon.py install     # disabled; reports manual startup policy
  python scripts/browser/cdp/cdp_daemon.py uninstall   # remove legacy startup wrapper
  python scripts/browser/cdp/cdp_daemon.py _run        # 내부 전용 (데몬 본체 직접 실행)
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.session import browser_lifecycle as lifecycle  # noqa: E402
from scripts.browser.session.browser_paths import find_chrome, find_edge  # noqa: E402
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed  # noqa: E402
from scripts.common.config import CDP_BROWSER_POLICY, CDP_HOST, CDP_PORT  # noqa: E402

# ── 설정 ─────────────────────────────────────────────────────────────
DAEMON_STATE_FILE = ROOT / "data" / "cdp_daemon_state.json"
DAEMON_LOG_FILE = ROOT / "data" / "logs" / "cdp_daemon.log"
# 프로필 경로 단일화: HAEHAN_CDP_PROFILE(앱·런처 공통 단일 출처) 우선. cdp_force_start.py·cdp_manager.js 와 동일.
_PROFILE_ENV = os.environ.get("HAEHAN_CDP_PROFILE", "").strip()
PROFILE_DIR = Path(_PROFILE_ENV) if _PROFILE_ENV else (ROOT / "data" / "cdp_profile" / "ai_chrome")
BROWSER_TYPE = os.environ.get("CDP_BROWSER", "auto")
TASK_NAME = "HaehanCdpDaemon"  # Task Scheduler 작업명
MAX_RESTART = int(os.environ.get("CDP_MAX_RESTART", "10"))  # 최대 재시작 횟수
# 유휴 자동 종료 — CDP 포트에 외부 연결이 N초 동안 하나도 없으면 Chrome·데몬 스스로 종료(기본 15분).
CDP_IDLE_TIMEOUT = int(os.environ.get("CDP_IDLE_TIMEOUT_SECONDS", "900"))
# 단일 인스턴스 락 — ROOT(저장소 경로) 기준이 아니라 OS 공용 임시 폴더 기준이라, 이 코드를 체크아웃한
# worktree 가 몇 개든 포트 하나당 락 파일 하나를 공유한다(대표님 지시: 다른 경로의 데몬이 이미
# 이 포트를 쓰면 시작 안 함).
_SINGLETON_LOCK_FILE = Path(tempfile.gettempdir()) / f"haehan_cdp_daemon_{CDP_PORT}.lock"

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
    running: bool = False
    pid: int = 0
    chrome_pid: int = 0
    popup_monitor_pid: int = 0
    chrome_ui_monitor_pid: int = 0
    cdp_port: int = CDP_PORT
    browser_context: str = "inactive"  # active / inactive
    started_at: str = ""
    last_heartbeat: str = ""
    last_error: str = ""
    restart_count: int = 0
    browser_kind: str = ""
    browser_exe: str = ""
    profile_dir: str = ""
    last_active_at: str = ""  # 마지막으로 CDP 포트에 외부 연결이 있었던 시각(유휴 자동 종료 판정용)


def _save_state(s: DaemonState) -> None:
    DAEMON_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_STATE_FILE.write_text(json.dumps(s.__dict__, indent=2), encoding="utf-8")


def _load_state() -> DaemonState:
    if not DAEMON_STATE_FILE.exists():
        return DaemonState()
    try:
        data = json.loads(DAEMON_STATE_FILE.read_text(encoding="utf-8"))
        return DaemonState(**{k: v for k, v in data.items() if k in DaemonState.__dataclass_fields__})
    except Exception:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        return DaemonState()


# ── 단일 인스턴스 락(여러 worktree 가 같은 CDP_PORT 를 중복 기동하지 못하게) ──────────
def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_singleton_lock() -> tuple[int, str] | None:
    try:
        lines = _SINGLETON_LOCK_FILE.read_text(encoding="utf-8").splitlines()
        return int(lines[0]), (lines[1] if len(lines) > 1 else "")
    except (OSError, ValueError, IndexError):
        return None


def _singleton_lock_holder() -> tuple[int, str] | None:
    """락 파일의 PID 가 아직 살아 있으면 (pid, started) 를, 죽었거나 락이 없으면 None."""
    info = _read_singleton_lock()
    if info is None:
        return None
    pid, started = info
    return (pid, started) if _pid_alive(pid) else None


def _acquire_singleton_lock() -> bool:
    """이 PID 가 CDP_PORT 의 유일한 데몬임을 선언한다. 다른(죽지 않은) PID 가 이미 들고 있으면 거부."""
    holder = _singleton_lock_holder()
    if holder is not None and holder[0] != os.getpid():
        log.warning(
            "[SINGLETON] 다른 CDP 데몬(PID=%d, 시작=%s)이 이미 포트 %d 를 쓰는 중 — 시작 안 함",
            holder[0], holder[1], CDP_PORT,
        )
        return False
    tmp = _SINGLETON_LOCK_FILE.with_suffix(".tmp")
    tmp.write_text(f"{os.getpid()}\n{datetime.now(UTC).isoformat()}\n", encoding="utf-8")
    os.replace(tmp, _SINGLETON_LOCK_FILE)  # 원자적 쓰기(임시 파일 후 교체)
    return True


def _release_singleton_lock() -> None:
    info = _read_singleton_lock()
    if info is not None and info[0] == os.getpid():
        try:
            _SINGLETON_LOCK_FILE.unlink()
        except OSError:
            pass


# ── 유휴 자동 종료 — CDP 포트에 들어온 외부 연결 수(우리 자신의 헬스체크 프로브는 제외) ──
def _external_cdp_connection_count(port: int = CDP_PORT) -> int:
    """port 로 들어온 ESTABLISHED TCP 연결 중, 이 프로세스(데몬 자신의 헬스체크 프로브) 소유가
    아닌 것의 수. psutil 이 없으면(드묾) 셀 수 없으니 항상 활동 중(0 아님)으로 보수적으로 본다
    — 측정 못한다고 유휴로 오판해 끄면 안 되기 때문."""
    try:
        import psutil
    except ImportError:
        return 1
    own_pid = os.getpid()
    try:
        conns = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError):
        return 1
    count = 0
    for c in conns:
        if c.status != psutil.CONN_ESTABLISHED or not c.laddr or c.laddr.port != port:
            continue
        if c.pid == own_pid:
            continue
        count += 1
    return count


# ── 브라우저 탐색 & 실행 ─────────────────────────────────────────────
def _find_browser(browser_type: str = "auto") -> tuple[str, str]:
    if browser_type == "chrome":
        exe = find_chrome()
        if not exe:
            raise FileNotFoundError("Chrome을 찾을 수 없습니다.")
        return exe, "chrome"
    elif browser_type == "edge":
        exe = find_edge()
        if not exe:
            raise FileNotFoundError("Edge를 찾을 수 없습니다.")
        return exe, "edge"
    else:
        exe = find_chrome()
        if exe:
            return exe, "chrome"
        exe = find_edge()
        if exe:
            return exe, "edge"
        raise FileNotFoundError("Chrome 또는 Edge를 찾을 수 없습니다.")


_WIN_LEFT, _WIN_TOP, _WIN_W, _WIN_H = 100, 50, 1440, 900


def _sanitize_chrome_prefs() -> None:
    """Chrome Preferences 패치: 비정상 종료 흔적 제거 + 창 위치 고정."""
    prefs = PROFILE_DIR / "Default" / "Preferences"
    if not prefs.exists():
        return
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
        profile = data.setdefault("profile", {})
        changed = False
        if profile.get("exit_type") != "Normal":
            profile["exit_type"] = "Normal"
            changed = True
        if profile.get("exited_cleanly") is not True:
            profile["exited_cleanly"] = True
            changed = True
        # 창 위치 고정 — Chrome은 마지막 위치를 Prefs에 저장하고 시작 시 복원.
        # --window-position 플래그보다 이 값이 우선되므로 직접 패치.
        browser = data.setdefault("browser", {})
        placement = browser.get("window_placement", {})
        need_fix = (
            placement.get("left", 0) > 3000
            or placement.get("top", 0) > 3000
            or placement.get("left", 0) < -100
            or placement.get("top", 0) < -100
            or placement.get("maximized") is True
        )
        if need_fix:
            browser["window_placement"] = {
                "bottom": _WIN_TOP + _WIN_H,
                "left": _WIN_LEFT,
                "maximized": False,
                "right": _WIN_LEFT + _WIN_W,
                "top": _WIN_TOP,
                "work_area_bottom": 1080,
                "work_area_left": 0,
                "work_area_right": 1920,
                "work_area_top": 0,
            }
            changed = True
        if changed:
            prefs.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            log.info(
                "[BROWSER] Preferences 정상화 (exit_type=Normal, window=%dx%d@%d,%d)",
                _WIN_W,
                _WIN_H,
                _WIN_LEFT,
                _WIN_TOP,
            )
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        log.warning("[BROWSER] Preferences 패치 실패 (무시): %s", e)


def _launch_chrome(port: int = CDP_PORT) -> subprocess.Popen:
    assert_browser_launch_allowed(component="scripts.browser.cdp.cdp_daemon", action="chrome_cdp_launch")
    exe, kind = _find_browser(BROWSER_TYPE)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _sanitize_chrome_prefs()
    args = [
        exe,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        # 세션 복원/충돌 복구 풍선 차단 (Chrome chrome UI는 popup_monitor 범위 밖)
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--disable-features=InfoBars,SessionCrashedBubble",
        # 이전 세션 복원 스위치(값 없이): 로그인(세션 쿠키)을 재시작 뒤에도 유지한다. 복원된 옛 탭은 시작 직후 close_stale_tabs 가 정리한다. 이전에 쓰던 `=false` 형태는 값과 무관하게 켜지는 스위치라 오해를 부르는 잘못된 표기였다.
        *lifecycle.session_args(CDP_BROWSER_POLICY),
        "--window-position=100,50",
        "--window-size=1280,900",
        "--force-device-scale-factor=1.5",
    ]
    log.info("[BROWSER] 종류=%s port=%d profile=%s", kind, port, PROFILE_DIR)
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("[BROWSER] PID=%d", proc.pid)
    return proc


def _record_browser_launch_metadata() -> None:
    try:
        exe, kind = _find_browser(BROWSER_TYPE)
        _state.browser_exe = exe
        _state.browser_kind = kind
    except Exception:  # noqa: BLE001 - 이미 원하는 상태(프로세스 종료됨/응답없음)인 경우의 정상 흐름 — 무시해도 안전(2026-09-28 검토)
        pass
    _state.profile_dir = str(PROFILE_DIR)


def _is_cdp_ready(port: int = CDP_PORT, timeout: int = 15) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://{CDP_HOST}:{port}/json/version", timeout=2)
            return True
        except Exception:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
            time.sleep(0.5)
    return False


def _cdp_json(path: str, *, port: int = CDP_PORT) -> Any:
    import urllib.request

    with urllib.request.urlopen(f"http://{CDP_HOST}:{port}{path}", timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _process_info(pid: int) -> dict[str, str]:
    if not pid:
        return {}
    if sys.platform != "win32":
        return {}
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f'Get-CimInstance Win32_Process -Filter "ProcessId={pid}" | '
                "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
            ),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=5)
        if r.returncode != 0 or not r.stdout.strip():
            return {}
        data = json.loads(r.stdout)
        if not isinstance(data, dict):
            return {}
        return {
            "pid": str(data.get("ProcessId") or ""),
            "exe": str(data.get("ExecutablePath") or ""),
            "command_line": str(data.get("CommandLine") or ""),
        }
    except Exception:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        return {}


def _extract_arg(command_line: str, name: str) -> str:
    pattern = rf'"?--{re.escape(name)}=([^"]+)"?|--{re.escape(name)}=([^\s]+)'
    m = re.search(pattern, command_line)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").strip()


def _profile_session_files(profile_dir: Path) -> list[str]:
    sessions_dir = profile_dir / "Default" / "Sessions"
    if not sessions_dir.exists():
        return []
    try:
        return [p.name for p in sorted(sessions_dir.iterdir()) if p.is_file()]
    except Exception:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        return []


# ── 데몬 본체 ─────────────────────────────────────────────────────────
_stop_event = threading.Event()
_state = DaemonState()


@dataclass
class _Procs:
    """데몬이 띄운 프로세스 보관(모듈 전역을 `global` 로 다시 대입하지 않고 속성으로 바꾼다)."""

    chrome: subprocess.Popen | None = None
    popup_monitor: subprocess.Popen | None = None


_procs = _Procs()


def _launch_background_python(args: list[str]) -> subprocess.Popen:
    """Launch a repo helper in a detached child process."""
    python_exe = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = python_exe.parent / "pythonw.exe"
        if pythonw.exists():
            python_exe = pythonw
        return subprocess.Popen(
            [str(python_exe), *args],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        [str(python_exe), *args],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _start_popup_monitor_process() -> None:
    """Run popup monitor out-of-process to keep Playwright sync API isolated."""
    if _procs.popup_monitor and _procs.popup_monitor.poll() is None:
        return
    script = ROOT / "scripts" / "entry" / "cdp_cli.py"
    _procs.popup_monitor = _launch_background_python([str(script), "popup-monitor", "start", "2.0"])
    _state.popup_monitor_pid = _procs.popup_monitor.pid
    _save_state(_state)
    log.info("[popup_monitor] process started PID=%d", _procs.popup_monitor.pid)


def _stop_chrome(proc: subprocess.Popen | None) -> None:
    """Chrome 을 3단계로 닫는다(CDP 종료 → 종료 신호 → 강제) — 앞 단계일수록 쿠키가 디스크에 잘 남는다."""
    if not proc or proc.poll() is not None:
        return
    how = lifecycle.stop_browser(
        CDP_PORT,
        proc.pid,
        is_alive=lambda: proc.poll() is None,
        graceful_first=CDP_BROWSER_POLICY["graceful_stop_first"],
    )
    if how in ("signal", "forced"):  # CDP 정상 종료가 아니면 로그인(세션 쿠키)이 사라졌을 수 있다
        log.warning(
            "[CHROME] 정상 종료(CDP) 실패 → 종료 방식=%s PID=%d — 로그인 세션이 사라졌을 수 있습니다", how, proc.pid
        )
    else:
        log.info("[CHROME] 종료 방식=%s PID=%d", how, proc.pid)


def _stop_process(proc: subprocess.Popen | None, label: str) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        log.info("[%s] stopped PID=%d", label, proc.pid)
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        log.warning("[%s] graceful stop failed: %s", label, e)


def _heartbeat_probe(cdp_fail_streak: int, healthy_streak: int, healthy_reset_after: int) -> tuple[int, int]:
    """CDP 포트 ping 1회. 갱신된 (cdp_fail_streak, healthy_streak) 반환."""
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=2) as resp:
            if resp.status == 200:
                cdp_fail_streak = 0
                healthy_streak += 1
                if _state.browser_context != "active":
                    _state.browser_context = "active"
                    log.info("[HEARTBEAT] CDP 정상 복귀")
                if healthy_streak >= healthy_reset_after and _state.restart_count > 0:
                    log.info("[HEARTBEAT] 5분간 정상 — restart_count(%d) 초기화", _state.restart_count)
                    _state.restart_count = 0
                    healthy_streak = 0
            else:
                cdp_fail_streak += 1
                healthy_streak = 0
    except Exception:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        cdp_fail_streak += 1
        healthy_streak = 0
    return cdp_fail_streak, healthy_streak


def _restart_dead_monitors() -> None:
    """종료된 popup_monitor 보조 프로세스를 재시작. archive 아래 스크립트는 절대 실행하지 않는다."""
    if _procs.popup_monitor and _procs.popup_monitor.poll() is not None:
        log.warning("[HEARTBEAT] popup_monitor 종료 감지 → 자동 재시작")
        _state.popup_monitor_pid = 0
        try:
            _start_popup_monitor_process()
        except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 보조 프로세스 재시작 실패는 로그 후 진행, 결제·인증·원격쓰기 없음(2026-10-08 검토)
            log.warning("[HEARTBEAT] popup_monitor 재시작 실패: %s", e)


def _port_listening(port: int = CDP_PORT, timeout: float = 1.0) -> bool:
    """디버그 포트에 TCP 연결이 되는가 — 되면 Chrome 프로세스는 살아 있다(HTTP 응답만 느릴 수 있다)."""
    try:
        with socket.create_connection((CDP_HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


CDP_FAIL_THRESHOLD = 3  # 연속 응답 없음 3회(약 30초) — 포트가 닫혀 있으면(Chrome 종료) 바로 재시작
CDP_HUNG_THRESHOLD = (
    18  # 포트는 열려 있는데 응답만 없을 땐 약 3분까지 기다린다(살아있는 Chrome 과 열린 탭을 죽이지 않는다)
)


def _should_stop_daemon(fail_streak: int, port_open: bool) -> bool:
    """데몬 종료 판정(순수). 포트가 닫혔다 = Chrome 이 없다(사용자가 닫았거나 죽음) → Chrome 을 다시 띄우지 않고 데몬을 끝낸다.

    사용자 종료와 크래시를 구분할 수 없으므로 재기동하지 않는다(2026-10-08 대표님 지시). 포트가 열려 있으면 응답이 느린
    살아있는 Chrome 이므로 종료하지 않는다(2026-10-05 실측: 응답 지연만으로 Chrome 을 죽여 탭이 날아갔다).
    """
    return fail_streak >= CDP_FAIL_THRESHOLD and not port_open


def _heartbeat_loop() -> None:
    """헬스체크 — CDP 포트가 닫히면(Chrome 종료) Chrome 을 다시 띄우지 않고 데몬을 종료한다.

    포트는 열려 있는데 응답만 없으면 기다리기만 한다(재시작 없음).
    """

    cdp_fail_streak = 0
    healthy_streak = 0
    HEALTHY_RESET_AFTER = 30  # 30회 연속(약 5분) 정상이면 restart_count 초기화

    while not _stop_event.is_set():
        try:
            _state.last_heartbeat = datetime.now(UTC).isoformat()
            cdp_fail_streak, healthy_streak = _heartbeat_probe(cdp_fail_streak, healthy_streak, HEALTHY_RESET_AFTER)

            if cdp_fail_streak >= CDP_FAIL_THRESHOLD:
                if _should_stop_daemon(cdp_fail_streak, _port_listening()):
                    log.warning("[HEARTBEAT] CDP 포트 %d 닫힘(Chrome 종료) — 재기동하지 않고 데몬을 종료합니다", CDP_PORT)
                    _state.browser_context = "inactive"
                    _state.last_error = "chrome_closed_daemon_stopping"
                    _save_state(_state)
                    _stop_event.set()
                    return
                if cdp_fail_streak == CDP_FAIL_THRESHOLD:
                    log.warning("[HEARTBEAT] CDP 포트 %d 응답이 느리지만 포트는 열려 있어 기다립니다(재시작 없음)", CDP_PORT)

            _restart_dead_monitors()

            if _check_idle_and_maybe_shutdown():
                break

            _save_state(_state)
        except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
            log.error("[HEARTBEAT] 오류: %s", e)
        _stop_event.wait(timeout=10)


def _check_idle_and_maybe_shutdown() -> bool:
    """CDP 포트에 외부 연결이 CDP_IDLE_TIMEOUT 초 동안 하나도 없으면 데몬 전체를 종료한다
    (대표님 지시 ②: 유휴면 크롬·데몬 스스로 종료). 종료를 트리거했으면 True."""
    if CDP_IDLE_TIMEOUT <= 0:
        return False  # 0 이하면 유휴 종료 기능 끔
    now = datetime.now(UTC)
    if _external_cdp_connection_count() > 0:
        _state.last_active_at = now.isoformat()
        return False
    try:
        last_active = datetime.fromisoformat(_state.last_active_at) if _state.last_active_at else now
    except ValueError:
        last_active = now
        _state.last_active_at = now.isoformat()
    idle_seconds = (now - last_active).total_seconds()
    if idle_seconds < CDP_IDLE_TIMEOUT:
        return False
    log.warning(
        "[IDLE] CDP 포트 %d 외부 연결 없음 %.0f초(기준 %d초) — 데몬 스스로 종료",
        CDP_PORT, idle_seconds, CDP_IDLE_TIMEOUT,
    )
    _stop_event.set()
    return True


def _signal_handler(signum: int, _frame: Any) -> None:
    log.info("신호 수신: %d → 종료", signum)
    _stop_event.set()


def _start_browser_watch() -> None:
    """탭·브라우저 프로세스 감시 로그(scripts/browser/cdp/browser_watch.py) 기동 — cdp_force_start 와 같은 감시를 데몬 경로에도 켠다. 실패해도 데몬은 계속."""
    try:
        from scripts.browser.cdp import browser_watch

        log.info("[WATCH] 브라우저 감시 로그 %s", "시작" if browser_watch.start() else "이미 실행 중")
    except Exception as e:  # noqa: BLE001 - 감시는 부가 기능, 실패해도 브라우저 관리는 계속
        log.warning("[WATCH] 브라우저 감시 로그 시작 실패(무시): %s", e)


def _start_monitor_processes() -> None:
    """popup_monitor 보조 프로세스 시작. 실패해도 데몬은 계속."""
    _start_browser_watch()

    # popup_monitor uses Playwright's sync API, so keep it in a separate
    # process. Running it in a daemon thread can collide with asyncio loops
    # created by other automation code in this process.
    try:
        _start_popup_monitor_process()
        log.info("✓ popup_monitor 자동 시작 완료 (poll=2.0s)")
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        log.warning("popup_monitor 시작 실패 (데몬은 계속): %s", e)


def _shutdown_daemon() -> None:
    """데몬 종료 정리 — 보조 프로세스/Chrome 종료 및 상태 저장."""
    log.info("데몬 종료 중...")
    _stop_process(_procs.popup_monitor, "popup_monitor")
    _stop_chrome(_procs.chrome)
    _state.running = False
    _state.chrome_pid = 0
    _state.popup_monitor_pid = 0
    _state.chrome_ui_monitor_pid = 0
    _state.browser_context = "inactive"
    _save_state(_state)
    _release_singleton_lock()
    log.info("데몬 종료 완료")


def run_daemon() -> None:

    log.info("=" * 60)
    log.info("  AI CDP 데몬 시작 (상시 실행 모드)")
    log.info("  PID: %d  CDP 포트: %d", os.getpid(), CDP_PORT)
    log.info("  프로필: %s", PROFILE_DIR)
    log.info("  최대 재시작: %d회", MAX_RESTART)
    log.info("  유휴 자동 종료: %d초", CDP_IDLE_TIMEOUT)
    log.info("=" * 60)

    if not _acquire_singleton_lock():
        log.error("다른 CDP 데몬이 이미 포트 %d 를 쓰는 중 — 이 인스턴스는 바로 종료", CDP_PORT)
        return

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    vars(_state).update(
        vars(
            DaemonState(
                running=True,
                pid=os.getpid(),
                cdp_port=CDP_PORT,
                browser_context="inactive",
                started_at=datetime.now(UTC).isoformat(),
                last_active_at=datetime.now(UTC).isoformat(),
                profile_dir=str(PROFILE_DIR),
            )
        )
    )  # 같은 객체를 제자리에서 다시 채운다(`__init__` 직접 호출은 안전하지 않다)
    _save_state(_state)

    # Chrome 실행
    try:
        _procs.chrome = _launch_chrome(CDP_PORT)
        _state.chrome_pid = _procs.chrome.pid
        _record_browser_launch_metadata()
        _save_state(_state)
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
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
        _procs.chrome.terminate()
        return

    log.info(
        "[CDP] 복원된 옛 탭 %d개 정리(시작 페이지 %s 탭 하나만 남김)",
        lifecycle.apply_start_policy(CDP_PORT, CDP_BROWSER_POLICY),
        CDP_BROWSER_POLICY["start_url"],
    )
    _state.browser_context = "active"
    _save_state(_state)
    log.info("✓ CDP 포트 %d 준비 완료", CDP_PORT)

    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    _start_monitor_processes()

    log.info("✓ 데몬 상시 대기 중...")
    try:
        while not _stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_daemon()


# ── CLI 명령 ─────────────────────────────────────────────────────────
def _probe_live_cdp(port: int = CDP_PORT) -> tuple[bool, str]:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{port}/json/version", timeout=2) as resp:
            if resp.status == 200:
                return True, "responding"
            return False, f"status={resp.status}"
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        return False, f"unavailable ({e})"


def cmd_start() -> None:
    live_cdp, live_detail = _probe_live_cdp(CDP_PORT)
    if live_cdp:
        state = _load_state()
        if state.running:
            print(f"CDP daemon-managed endpoint is already responding (port={CDP_PORT})")
        else:
            print(f"Live CDP endpoint is responding but daemon state is inactive (port={CDP_PORT})")
            print("Use current browser for read-only work, or run restart after closing the external CDP Chrome.")
        print(f"detail: {live_detail}")
        return
    import urllib.request

    # 이미 CDP 포트 응답 중이면 스킵
    try:
        urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=2)
        print(f"✓ CDP 데몬 이미 실행 중 (포트={CDP_PORT})")
        return
    except Exception:  # noqa: BLE001 - 이미 원하는 상태(프로세스 종료됨/응답없음)인 경우의 정상 흐름 — 무시해도 안전(2026-09-28 검토)
        pass

    # 다른 worktree 복사본이 띄운 데몬이 아직 살아 있으면(락 파일 PID 기준) 여기서 바로 거부 —
    # 자식 프로세스를 띄웠다가 자기 스스로 거부하고 조용히 종료하는 것보다 사용자에게 바로 알려준다.
    holder = _singleton_lock_holder()
    if holder is not None:
        print(f"CDP 데몬이 이미 다른 프로세스(PID={holder[0]}, 시작={holder[1]})로 포트 {CDP_PORT} 을 쓰는 중 — 시작 안 함")
        return

    assert_browser_launch_allowed(component="scripts.browser.cdp.cdp_daemon", action="cdp_daemon_start")

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
            how = lifecycle.stop_browser(
                CDP_PORT, state.chrome_pid, graceful_first=CDP_BROWSER_POLICY["graceful_stop_first"]
            )  # 쿠키가 디스크에 남도록 정상 종료부터 3단계
            print(f"✓ Chrome 종료 (PID={state.chrome_pid}, 방식={how})")
            stopped = True
        except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
            print(f"⚠  Chrome 종료 실패: {e}")

    # 데몬 프로세스 종료
    if state.popup_monitor_pid:
        try:
            os.kill(state.popup_monitor_pid, signal.SIGTERM)
            print(f"popup_monitor stopped (PID={state.popup_monitor_pid})")
            stopped = True
        except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
            print(f"popup_monitor stop failed: {e}")

    if state.pid and state.pid != os.getpid():
        try:
            os.kill(state.pid, signal.SIGTERM)
            print(f"✓ 데몬 종료 (PID={state.pid})")
            stopped = True
        except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
            print(f"⚠  데몬 종료 실패: {e}")

    state.running = False
    state.chrome_pid = 0
    state.popup_monitor_pid = 0
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
    probe_port = state.cdp_port or CDP_PORT
    live_cdp = False
    live_cdp_detail = "no response"
    try:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{probe_port}/json/version", timeout=2) as resp:
            live_cdp = resp.status == 200
            live_cdp_detail = "responding" if live_cdp else f"status={resp.status}"
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        live_cdp_detail = f"unavailable ({e})"
    print(f"live CDP:      {'yes' if live_cdp else 'no'}")
    print(f"live endpoint: http://{CDP_HOST}:{probe_port}  ({live_cdp_detail})")
    print(f"managed daemon:{' yes' if state.running else ' no'}")
    print(f"browser usable:{' yes' if live_cdp else ' no'}")
    print(f"daemon pid:    {state.pid or '-'}")
    print(f"chrome pid:    {state.chrome_pid or '-'}")
    print(f"popup pid:     {state.popup_monitor_pid or '-'}")
    print(f"browser state: {state.browser_context or 'unknown'}")
    print(f"started at:    {state.started_at or '-'}")
    print(f"heartbeat:     {state.last_heartbeat or '-'}")
    if state.last_error:
        print(f"last error:    {state.last_error}")
    vbs_path = _startup_folder() / f"{TASK_NAME}.vbs"
    print(f"autostart:     {'yes' if vbs_path.exists() else 'no'}")
    if live_cdp and not state.running:
        print("note: live browser is usable, but no daemon process is managing it.")
    return

    print("=" * 60)
    print("CDP 데몬 상태")
    print("=" * 60)
    print(f"실행:         {'✓ 예' if state.running else '✗ 아니오'}")

    if state.running:
        try:
            urllib.request.urlopen(f"http://{CDP_HOST}:{state.cdp_port}/json/version", timeout=2)
            cdp_ok = "✓ 응답 중"
        except Exception:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
            cdp_ok = "✗ 응답 없음"

        print(f"데몬 PID:     {state.pid}")
        print(f"Chrome PID:   {state.chrome_pid}")
        print(f"Popup PID:    {state.popup_monitor_pid}")
        print(f"CDP 포트:     {state.cdp_port}  ({cdp_ok})")
        print(f"브라우저:     {state.browser_context}")
        print(f"재시작 횟수:  {state.restart_count}")
        print(f"시작:         {state.started_at}")
        print(f"하트비트:     {state.last_heartbeat}")
        if state.last_error:
            print(f"마지막 오류: {state.last_error}")

    # 시작 프로그램 등록 여부 확인
    vbs_path = _startup_folder() / f"{TASK_NAME}.vbs"
    installed = vbs_path.exists()
    print(f"자동시작 등록: {'✓ 등록됨' if installed else '✗ 미등록'}")


def cmd_inspect() -> None:
    state = _load_state()
    proc = _process_info(state.chrome_pid)
    command_line = proc.get("command_line", "")
    profile_from_cmd = _extract_arg(command_line, "user-data-dir")
    port_from_cmd = _extract_arg(command_line, "remote-debugging-port")
    profile_dir = Path(profile_from_cmd or state.profile_dir or PROFILE_DIR)

    print("=" * 60)
    print("CDP browser inspect")
    print("=" * 60)
    print(f"daemon_pid:        {state.pid}")
    print(f"chrome_pid:        {state.chrome_pid}")
    print(f"browser_kind:      {state.browser_kind or '(unknown)'}")
    print(f"browser_exe:       {proc.get('exe') or state.browser_exe or '(unknown)'}")
    print(f"cdp_endpoint:      http://{CDP_HOST}:{state.cdp_port}")
    print(f"port_from_cmd:     {port_from_cmd or '(missing)'}")
    print(f"profile_dir:       {profile_dir}")
    print(f"command_line:      {command_line or '(unavailable)'}")

    session_files = _profile_session_files(profile_dir)
    print(f"profile_sessions:  {len(session_files)} file(s)")
    for name in session_files[-6:]:
        print(f"  - {name}")

    try:
        version = _cdp_json("/json/version", port=state.cdp_port)
        print(f"cdp_browser:       {version.get('Browser', '')}")
        print(f"websocket:         {version.get('webSocketDebuggerUrl', '')}")
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        print(f"cdp_browser:       unavailable ({e})")

    try:
        tabs = _cdp_json("/json/list", port=state.cdp_port)
        print(f"tabs:              {len(tabs)}")
        for idx, tab in enumerate(tabs, start=1):
            url = tab.get("url", "")
            title = tab.get("title", "")
            marker = ""
            if "naver.com/NOTICE/" in url:
                marker = " [naver notice]"
            elif "naver.com" in url:
                marker = " [naver]"
            print(f"  {idx}. {title[:60]}{marker}")
            print(f"     {url}")
    except Exception as e:  # noqa: BLE001 - CDP 데몬 생명주기 관리 — 로컬 Chrome 프로세스/파일 상태 확인은 실패 종류가 다양해(파일없음/프로세스종료/포트미응답 등) 일괄 로그·기본값 폴백, 결제·인증·원격쓰기 없음(2026-09-28 검토)
        print(f"tabs:              unavailable ({e})")


def _startup_folder() -> Path:
    """현재 사용자 시작 프로그램 폴더 경로 (Windows 전용)."""
    if sys.platform != "win32":
        raise RuntimeError("시작 프로그램 등록은 Windows 전용입니다")
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def cmd_install() -> None:
    """Report the manual-start policy; legacy autostart registration is disabled."""
    print("CDP autostart install is disabled by the target-app scope baseline.")
    print("Use explicit, task-scoped start only: python scripts/browser/cdp/cdp_daemon.py start")
    print("To remove an old startup wrapper, run: python scripts/browser/cdp/cdp_daemon.py uninstall")


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


def _command_table() -> dict:
    """CLI 명령 -> 실행 함수 표. 호출 시점에 이름을 조회한다."""
    return {
        "start": lambda: cmd_start(),
        "stop": lambda: cmd_stop(),
        "restart": lambda: cmd_restart(),
        "status": lambda: cmd_status(),
        "inspect": lambda: cmd_inspect(),
        "install": lambda: cmd_install(),
        "uninstall": lambda: cmd_uninstall(),
        "logs": lambda: cmd_logs(),
        "_run": lambda: run_daemon(),  # 내부 전용
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    handler = _command_table().get(sys.argv[1])
    if handler is None:
        print(f"알 수 없는 명령: {sys.argv[1]}")
        print(__doc__)
        return
    handler()


if __name__ == "__main__":
    main()
