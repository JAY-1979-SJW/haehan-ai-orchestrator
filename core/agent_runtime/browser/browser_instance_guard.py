"""자동화 전용 Chrome 인스턴스 가드.

목표:
  - 자동화 Chrome 의 실행 경로/프로필/CDP 포트를 고정값으로 인식.
  - browser_start 전 자동화 Chrome 개수를 확인하여 0/1/>=2 분기.
  - PID/lock 파일과 CDP /json/version alive 체크로 stale 정리.
  - 사용자의 일반 Chrome 은 검사·종료 대상에서 제외.

본 모듈은 실제 정책 enforcement 가 아니라 "기능 안정화" 가드다.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_BOOT = Path(__file__).resolve().parents[3]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

# ── 고정값 (기존 cdp_daemon / config 와 일치) ───────────────────────────

_ROOT = repo_root()

# 자동화 Chrome 식별 기준값.
# 기존 scripts/browser/cdp/cdp_daemon.py 가 사용하는 PROFILE_DIR / CDP_PORT 와 일치.
DEFAULT_PROFILE_DIR = _ROOT / "data" / "cdp_profile" / "ai_chrome"
DEFAULT_CDP_PORT = 9222

# 본 모듈이 발급/관리하는 lock/pid 등 runtime 파일 위치.
DEFAULT_STATE_DIR = _ROOT / ".runtime" / "browser"
PID_FILE_NAME = "chrome.pid"
LOCK_FILE_NAME = "chrome.lock"
SNAPSHOT_FILE_NAME = "session_snapshot.json"


# ── 결과 코드 ────────────────────────────────────────────────────────

ACTION_START_NEW = "start_new"
ACTION_ATTACH_EXISTING = "attach_existing"
ACTION_ATTACH_ORPHAN_CDP = "attach_orphan_cdp"
ACTION_BLOCKED_BY_LOCK = "blocked_by_lock"
ACTION_ERROR_MULTIPLE = "error_multiple"

ERROR_MULTIPLE_BROWSERS = "MULTIPLE_AUTOMATION_BROWSERS"
WARN_ORPHANED_CDP_OR_PROFILE = "ORPHANED_CDP_OR_PROFILE"


# ── 데이터 ───────────────────────────────────────────────────────────


@dataclass
class GuardPaths:
    profile_dir: Path
    state_dir: Path
    cdp_port: int

    @property
    def pid_file(self) -> Path:
        return self.state_dir / PID_FILE_NAME

    @property
    def lock_file(self) -> Path:
        return self.state_dir / LOCK_FILE_NAME

    @property
    def snapshot_file(self) -> Path:
        return self.state_dir / SNAPSHOT_FILE_NAME


@dataclass
class AutomationProcess:
    pid: int
    cmdline: str
    has_profile_match: bool
    has_port_match: bool

    @property
    def is_automation(self) -> bool:
        return self.has_profile_match and self.has_port_match

    @property
    def is_orphan_partial(self) -> bool:
        return self.has_profile_match ^ self.has_port_match


@dataclass
class BrowserStartDecision:
    action: str
    count: int = 0
    cdp_alive: bool = False
    pid_file_pid: int = 0
    lock_active: bool = False
    orphan_partials: int = 0
    error: str = ""
    message_ko: str = ""
    matched_pids: list[int] = field(default_factory=list)


# ── 경로 해석 ────────────────────────────────────────────────────────


def resolve_paths(
    *,
    profile_dir: Path | str | None = None,
    state_dir: Path | str | None = None,
    cdp_port: int | None = None,
) -> GuardPaths:
    pd = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
    sd = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
    port = int(cdp_port) if cdp_port else DEFAULT_CDP_PORT
    sd.mkdir(parents=True, exist_ok=True)
    return GuardPaths(profile_dir=pd, state_dir=sd, cdp_port=port)


# ── Chrome 프로세스 enumerate (인젝션 가능) ─────────────────────────


def _enum_chrome_psutil() -> list[tuple[int, str]] | None:
    """psutil 로 열거. 실패하면 None (다음 폴백으로)."""
    try:
        import psutil  # type: ignore

        out: list[tuple[int, str]] = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (p.info.get("name") or "").lower()
                if "chrome" not in name and "chromium" not in name and "msedge" not in name:
                    continue
                cmd = " ".join(p.info.get("cmdline") or [])
                out.append((int(p.info["pid"]), cmd))
            except Exception:  # noqa: BLE001, S112
                continue
        return out
    except Exception:  # noqa: BLE001
        return None


def _enum_chrome_wmic() -> list[tuple[int, str]]:
    """Windows wmic 폴백."""
    try:
        import subprocess

        r = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "name='chrome.exe' or name='msedge.exe'",
                "get",
                "ProcessId,CommandLine",
                "/format:csv",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
        )
        out: list[tuple[int, str]] = []
        for line in (r.stdout or "").splitlines():
            parts = line.split(",")
            if len(parts) < 3:
                continue
            cmd = parts[1].strip()
            try:
                pid = int(parts[2].strip())
            except ValueError:
                continue
            out.append((pid, cmd))
        return out
    except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
        return []


def _enum_chrome_ps() -> list[tuple[int, str]]:
    """POSIX ps 폴백."""
    try:
        import subprocess

        r = subprocess.run(
            ["ps", "-eo", "pid,command"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
        )
        out: list[tuple[int, str]] = []
        for line in (r.stdout or "").splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            head, _, cmd = line.partition(" ")
            cmd = cmd.strip()
            low = cmd.lower()
            if "chrome" not in low and "chromium" not in low:
                continue
            try:
                pid = int(head)
            except ValueError:
                continue
            out.append((pid, cmd))
        return out
    except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
        return []


def _enumerate_chrome_processes_default() -> list[tuple[int, str]]:
    """OS 별 Chrome 프로세스 목록 (pid, cmdline) 을 반환한다.

    psutil 우선, 없으면 Windows 는 wmic, 나머지는 ps 폴백.
    """
    out = _enum_chrome_psutil()
    if out is not None:
        return out

    # Windows wmic fallback
    if os.name == "nt":
        return _enum_chrome_wmic()

    return _enum_chrome_ps()


_process_enumerator: Callable[[], list[tuple[int, str]]] = _enumerate_chrome_processes_default


def set_process_enumerator(fn: Callable[[], list[tuple[int, str]]]) -> None:
    """테스트 전용 — 프로세스 열거 함수 주입."""
    global _process_enumerator
    _process_enumerator = fn


def reset_process_enumerator() -> None:
    global _process_enumerator
    _process_enumerator = _enumerate_chrome_processes_default


# ── 식별 ─────────────────────────────────────────────────────────────


def _normalize_for_match(s: str) -> str:
    return s.replace("\\", "/").lower()


def _has_profile_arg(cmdline: str, profile_dir: Path) -> bool:
    needle = _normalize_for_match(str(profile_dir))
    return needle in _normalize_for_match(cmdline)


def _has_port_arg(cmdline: str, port: int) -> bool:
    flag = f"--remote-debugging-port={port}"
    return flag in cmdline


def _is_chrome_child_process(cmdline: str) -> bool:
    """Chrome 자식 프로세스 식별.

    Chrome 의 renderer/gpu/utility/zygote 등 자식 프로세스는 부모의 cmdline
    인자(--user-data-dir / --remote-debugging-port)를 상속받는다.
    `--type=<X>` 플래그가 있으면 자식 프로세스로 분류 — 자동화 인스턴스
    카운트에서 제외한다. browser 본체에는 `--type` 플래그가 없다.
    """
    return "--type=" in cmdline


def list_automation_chrome_processes(paths: GuardPaths) -> list[AutomationProcess]:
    """자동화 Chrome 후보 프로세스 목록을 반환한다.

    is_automation=True 만 자동화로 인정. is_orphan_partial 은 둘 중 하나만 일치.
    """
    out: list[AutomationProcess] = []
    for pid, cmdline in _process_enumerator():
        has_profile = _has_profile_arg(cmdline, paths.profile_dir)
        has_port = _has_port_arg(cmdline, paths.cdp_port)
        if not (has_profile or has_port):
            continue
        # Chrome 자식(renderer/gpu/utility 등) 은 부모 cmdline 을 상속받으므로
        # `--type=` 플래그를 기준으로 제외한다. browser 본체만 카운트.
        if _is_chrome_child_process(cmdline):
            continue
        out.append(
            AutomationProcess(
                pid=pid,
                cmdline=cmdline,
                has_profile_match=has_profile,
                has_port_match=has_port,
            )
        )
    return out


def count_automation_browsers(paths: GuardPaths) -> tuple[int, int, list[int]]:
    """returns (count_full_match, count_orphan_partial, full_match_pids)."""
    procs = list_automation_chrome_processes(paths)
    full = [p for p in procs if p.is_automation]
    partial = [p for p in procs if p.is_orphan_partial]
    return len(full), len(partial), [p.pid for p in full]


# ── PID / lock ───────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(int(pid))
    except Exception:  # noqa: S110, BLE001
        pass
    if os.name == "nt":
        try:
            import subprocess

            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=3,
                encoding="utf-8",
            )
            return str(pid) in (r.stdout or "")
        except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def read_pid_file(paths: GuardPaths) -> int:
    if not paths.pid_file.exists():
        return 0
    try:
        return int(paths.pid_file.read_text(encoding="utf-8").strip() or "0")
    except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
        return 0


def write_pid_file(paths: GuardPaths, pid: int) -> None:
    paths.pid_file.write_text(str(int(pid)), encoding="utf-8")


def clear_pid_file(paths: GuardPaths) -> None:
    with contextlib.suppress(FileNotFoundError):
        paths.pid_file.unlink()


def cleanup_stale_pid(paths: GuardPaths) -> tuple[int, bool]:
    """returns (pid_in_file, was_stale_cleaned)."""
    pid = read_pid_file(paths)
    if pid <= 0:
        return 0, False
    if _pid_alive(pid):
        return pid, False
    clear_pid_file(paths)
    return pid, True


def write_lock_file(paths: GuardPaths, owner_pid: int) -> None:
    payload = {"pid": int(owner_pid), "ts": time.time()}
    # tmp 이름에 pid를 넣어 두 프로세스가 동시에 써도 서로의 tmp를 안 덮어쓰게 한다(T4 R11).
    tmp = paths.lock_file.with_suffix(paths.lock_file.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(paths.lock_file)


def read_lock_file(paths: GuardPaths) -> dict[str, Any]:
    if not paths.lock_file.exists():
        return {}
    try:
        return json.loads(paths.lock_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
        return {}


def clear_lock_file(paths: GuardPaths) -> None:
    with contextlib.suppress(FileNotFoundError):
        paths.lock_file.unlink()


def is_lock_active(paths: GuardPaths) -> bool:
    info = read_lock_file(paths)
    pid = int(info.get("pid", 0) or 0)
    if pid <= 0:
        return False
    if _pid_alive(pid):
        return True
    clear_lock_file(paths)
    return False


def try_acquire_lock(paths: GuardPaths, owner_pid: int) -> bool:
    """잠금을 원자적으로 시도 — 성공하면 True, 이미 살아있는 잠금이면 False(T4 R11).

    기존에는 `is_lock_active()`로 확인한 뒤 호출자가 Chrome 을 띄우고
    `write_lock_file()`로 무조건 덮어써서, 그 사이(확인→기동→쓰기)에 다른 프로세스가
    끼어들 수 있는 check-then-act 레이스가 있었다. 이 함수는 "죽은 잠금이면 치우고,
    O_CREAT|O_EXCL 로 새 잠금 파일을 원자적으로 만드는 데 성공한 경우에만 True"를
    돌려줘, 성공한 호출자만 Chrome을 띄우는 흐름으로 쓸 수 있게 한다
    (tools/gates/gate_core.py의 _opt_out_guard()와 같은 원자적 생성 패턴).
    기존 write_lock_file()/is_lock_active() 는 하위 호환을 위해 그대로 둔다.
    """
    if is_lock_active(paths):
        return False
    payload = {"pid": int(owner_pid), "ts": time.time()}
    try:
        fd = os.open(str(paths.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except PermissionError:
        # Windows: 방금 unlink 된 잠금 파일은 '삭제 보류' 상태라 같은 이름의 생성이
        # PermissionError 로 실패할 수 있다 — 잠금 중과 같은 뜻으로 처리.
        if os.name == "nt":
            return False
        raise
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload))
    return True


# ── CDP alive ────────────────────────────────────────────────────────

_cdp_probe: Callable[[int], bool] | None = None


def set_cdp_probe(fn: Callable[[int], bool] | None) -> None:
    """테스트 전용 — CDP alive probe 주입."""
    global _cdp_probe
    _cdp_probe = fn


def check_cdp_alive(port: int, timeout: float = 1.0) -> bool:
    if _cdp_probe is not None:
        try:
            return bool(_cdp_probe(port))
        except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
            return False
    try:
        import urllib.request

        with urllib.request.urlopen(
            f"http://127.0.0.1:{int(port)}/json/version",
            timeout=timeout,
        ) as resp:
            return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
        return False


# ── 의사결정 ─────────────────────────────────────────────────────────


def decide_browser_start(paths: GuardPaths) -> BrowserStartDecision:
    """browser_start 전 안전 판정.

    Returns:
        BrowserStartDecision — action 으로 분기.
    """
    full_count, partial_count, matched_pids = count_automation_browsers(paths)
    cdp_alive = check_cdp_alive(paths.cdp_port)

    if full_count >= 2:
        return BrowserStartDecision(
            action=ACTION_ERROR_MULTIPLE,
            count=full_count,
            cdp_alive=cdp_alive,
            orphan_partials=partial_count,
            matched_pids=matched_pids,
            error=ERROR_MULTIPLE_BROWSERS,
            message_ko=(
                f"자동화 Chrome 이 {full_count}개 실행 중 입니다. 새로 시작하지 않고 사용자 정리 후 재시도해 주세요."
            ),
        )

    pid_in_file, _stale_cleaned = cleanup_stale_pid(paths)
    lock_active = is_lock_active(paths)

    if full_count == 1:
        # 이미 1개 살아있음 → attach/reuse
        return BrowserStartDecision(
            action=ACTION_ATTACH_EXISTING,
            count=1,
            cdp_alive=cdp_alive,
            pid_file_pid=pid_in_file,
            lock_active=lock_active,
            orphan_partials=partial_count,
            matched_pids=matched_pids,
            message_ko="자동화 Chrome 이 이미 실행 중 입니다 — 기존 인스턴스에 연결합니다.",
        )

    if cdp_alive:
        # CDP 살아있는데 매칭 프로세스 0 → orphan CDP
        return BrowserStartDecision(
            action=ACTION_ATTACH_ORPHAN_CDP,
            count=0,
            cdp_alive=True,
            pid_file_pid=pid_in_file,
            lock_active=lock_active,
            orphan_partials=partial_count,
            message_ko="CDP 가 살아 있으나 자동화 프로필 프로세스가 없습니다 — orphan 으로 attach 시도합니다.",
        )

    if lock_active:
        return BrowserStartDecision(
            action=ACTION_BLOCKED_BY_LOCK,
            count=0,
            cdp_alive=False,
            pid_file_pid=pid_in_file,
            lock_active=True,
            orphan_partials=partial_count,
            error="LOCK_ACTIVE",
            message_ko="다른 프로세스가 브라우저 시작을 진행 중입니다 — 잠시 후 다시 시도해 주세요.",
        )

    return BrowserStartDecision(
        action=ACTION_START_NEW,
        count=0,
        cdp_alive=False,
        pid_file_pid=pid_in_file,
        lock_active=False,
        orphan_partials=partial_count,
        message_ko="자동화 Chrome 미실행 — 새 인스턴스를 시작합니다.",
    )


# ── 종료 ─────────────────────────────────────────────────────────────


def close_all_cdp_targets(cdp_port: int) -> list[str]:
    """CDP /json/list 의 모든 page 타입 target 을 /json/close 로 닫는다.

    Returns 닫힌 target_id 목록 (best-effort).
    """
    import json as _json
    import urllib.parse
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{int(cdp_port)}/json/list",
            timeout=2.0,
        ) as resp:
            rows = _json.loads(resp.read().decode("utf-8") or "[]")
    except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
        return []

    closed: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "page":
            continue
        tid = str(row.get("id", "") or "")
        if not tid:
            continue
        try:
            quoted = urllib.parse.quote(tid, safe="")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{int(cdp_port)}/json/close/{quoted}",
                timeout=2.0,
            ):
                closed.append(tid)
        except Exception:  # noqa: BLE001, S112
            continue
    return closed


def quit_automation_browsers(
    paths: GuardPaths,
    *,
    kill_fn: Callable[[int], bool] | None = None,
    close_targets_first: bool = True,
) -> dict[str, Any]:
    """고정 프로필/포트와 일치하는 자동화 Chrome 만 종료한다.

    사용자의 일반 Chrome 은 절대 종료 대상이 아니다.
    종료 전 CDP /json/close 로 모든 page target 을 닫아 다음 시작 시
    세션 복원으로 이전 탭이 되살아나는 것을 방지한다.
    """
    closed_targets: list[str] = []
    if close_targets_first:
        try:
            closed_targets = close_all_cdp_targets(paths.cdp_port)
        except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
            closed_targets = []

    procs = list_automation_chrome_processes(paths)
    targets = [p for p in procs if p.is_automation]

    def _default_kill(pid: int) -> bool:
        try:
            import psutil  # type: ignore

            psutil.Process(int(pid)).terminate()
            return True
        except Exception:  # noqa: S110, BLE001
            pass
        if os.name == "nt":
            try:
                import subprocess

                r = subprocess.run(
                    ["taskkill", "/PID", str(int(pid)), "/F"],
                    capture_output=True,
                    timeout=5,
                )
                return r.returncode == 0
            except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
                return False
        try:
            import signal

            os.kill(int(pid), signal.SIGTERM)
            return True
        except Exception:  # noqa: BLE001 - 로컬 Chrome 자동화 프로세스 생명주기 관리(PID/락파일/CDP 상태 확인·종료) — 실패는 안전한 기본값(False/빈 리스트/0)으로 폴백, 여러 방법(psutil→wmic→SIGTERM)을 순차 시도, 원격 쓰기·결제 없음(2026-09-28 검토)
            return False

    killer = kill_fn or _default_kill
    killed: list[int] = []
    failed: list[int] = []
    for p in targets:
        ok = bool(killer(p.pid))
        (killed if ok else failed).append(p.pid)

    clear_pid_file(paths)
    clear_lock_file(paths)
    with contextlib.suppress(FileNotFoundError):
        paths.snapshot_file.unlink()

    return {
        "ok": not failed,
        "killed_pids": killed,
        "failed_pids": failed,
        "count_before": len(targets),
        "count_after_estimate": len(failed),
        "closed_targets": closed_targets,
    }
