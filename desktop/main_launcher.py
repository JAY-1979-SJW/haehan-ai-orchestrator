"""HaehanAI 단일 exe 통합 launcher (HAEHAN_SINGLE_EXE_LAUNCHER_FOUNDATION_01).

목표:
    HaehanAI.exe 단일 진입점의 골조. 인자 파싱, 모드 분기, 단일 인스턴스 락,
    lifecycle hook 만 구현. 실제 Tray/Admin 통합은 후속 공정에서 진행.

본 모듈은 기존 진입점을 깨지 않는다:
    - desktop/webview_app_pywebview.py (Desktop.exe 진입점)
    - local_agent/desktop_launcher.py (Agent.exe 진입점)

위 두 모듈은 그대로 동작하며, 본 launcher는 통합 후보 진입점일 뿐이다.

CLI 모드:
    HaehanAI.exe                  → Tray Mode (기본)
    HaehanAI.exe --tray           → Tray Mode (명시)
    HaehanAI.exe --admin          → Admin Mode (role 확인 후)
    HaehanAI.exe --diagnostics    → 진단 정보 stdout (마스킹)
    HaehanAI.exe --version        → 버전 출력 후 종료
    HaehanAI.exe --reset-lock     → stale lock 강제 제거
    HaehanAI.exe --help           → 사용법

보안:
    device_token / registration_code / API key 원문 절대 출력 금지.
    lock 파일에 secret 저장 금지.
    local-only bypass 금지 — 127.0.0.1이라도 role 검사 통과 필요.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

__version__ = "0.2.0-launcher-foundation"

logger = logging.getLogger(__name__)


# ── 모드 ──────────────────────────────────────────────────────────────────

class AppMode(str, Enum):
    TRAY = "tray"
    ADMIN = "admin"
    DIAGNOSTICS = "diagnostics"
    VERSION = "version"
    RESET_LOCK = "reset-lock"


# ── 경로 ──────────────────────────────────────────────────────────────────

def app_root() -> Path:
    """exe/소스 모두에서 프로젝트 루트 반환."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def user_data_dir() -> Path:
    """%LOCALAPPDATA%/HaehanAI (Windows) — exe 폴더와 분리, 사용자별."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / ".local" / "share")
    p = Path(base) / "HaehanAI"
    p.mkdir(parents=True, exist_ok=True)
    return p


def lock_path() -> Path:
    return user_data_dir() / "app.lock"


def log_dir() -> Path:
    d = app_root() / "data" / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        # 권한 문제 시 user data로 fallback
        d = user_data_dir() / "logs"
        d.mkdir(parents=True, exist_ok=True)
    return d


# ── 로깅 ──────────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> None:
    """콘솔 + 파일 동시 로깅. exe / 소스 모두 동작."""
    import logging.handlers
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir() / "haehan_launcher.log",
            maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.root.addHandler(file_handler)
    except Exception:
        pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


# ── 단일 인스턴스 락 ──────────────────────────────────────────────────────

@dataclass
class LockState:
    acquired: bool
    pid: int
    stale: bool
    path: str
    error: str = ""


def _pid_alive(pid: int) -> bool:
    """PID가 살아있는지 확인. 실패 시 False."""
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY_LIMITED = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
            if not h:
                return False
            try:
                code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                if not ok:
                    return False
                STILL_ACTIVE = 259
                return code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _read_lock() -> Optional[int]:
    """lock 파일에서 PID 읽기. 없으면 None."""
    p = lock_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        return pid if pid > 0 else None
    except Exception:
        return None


def _write_lock() -> None:
    """현재 PID + 시작 시각을 lock에 기록. secret 저장 금지."""
    payload = {
        "pid": os.getpid(),
        "started_at": datetime.now().isoformat(),
        "version": __version__,
    }
    lock_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def acquire_lock(force: bool = False) -> LockState:
    """단일 인스턴스 락 획득.

    Returns:
        LockState.acquired=True 면 본 프로세스가 락을 소유.
        False 면 다른 인스턴스가 살아있어서 진입 불가.
    """
    existing_pid = _read_lock()
    p = lock_path()

    if existing_pid is None:
        # 락 없음 — 바로 획득
        try:
            _write_lock()
            return LockState(acquired=True, pid=os.getpid(), stale=False, path=str(p))
        except Exception as e:
            return LockState(acquired=False, pid=0, stale=False, path=str(p), error=str(e))

    # 락 존재 — PID 검사
    alive = _pid_alive(existing_pid)

    if not alive:
        # stale lock — 자동 정리 후 획득
        try:
            p.unlink(missing_ok=True)
            _write_lock()
            return LockState(acquired=True, pid=os.getpid(), stale=True, path=str(p))
        except Exception as e:
            return LockState(acquired=False, pid=existing_pid, stale=True, path=str(p), error=str(e))

    # 살아있는 PID — 강제 옵션 확인
    if force:
        try:
            p.unlink(missing_ok=True)
            _write_lock()
            return LockState(acquired=True, pid=os.getpid(), stale=False, path=str(p))
        except Exception as e:
            return LockState(acquired=False, pid=existing_pid, stale=False, path=str(p), error=str(e))

    return LockState(acquired=False, pid=existing_pid, stale=False, path=str(p))


def release_lock() -> None:
    """본 프로세스가 소유한 락 해제. 다른 프로세스 락은 건드리지 않음."""
    p = lock_path()
    existing_pid = _read_lock()
    if existing_pid == os.getpid():
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


def reset_lock() -> dict:
    """--reset-lock — stale 여부 무관하게 강제 제거."""
    p = lock_path()
    existed = p.exists()
    pid = _read_lock()
    try:
        p.unlink(missing_ok=True)
        return {"ok": True, "existed": existed, "pid": pid}
    except Exception as e:
        return {"ok": False, "error": str(e), "existed": existed, "pid": pid}


# ── lifecycle hooks ──────────────────────────────────────────────────────

def check_consent_hook() -> dict:
    """동의 상태 확인 hook. 실제 동의 창 표시는 후속 공정.

    설계서 §6 lifecycle 의 1번 단계. 현재는 consent.json 존재 여부만 확인.
    """
    consent_file = app_root() / "data" / "consent.json"
    if not consent_file.exists():
        return {"agreed": False, "needs_prompt": True, "source": "missing"}
    try:
        data = json.loads(consent_file.read_text(encoding="utf-8"))
        return {
            "agreed": bool(data.get("agreed")),
            "needs_prompt": not bool(data.get("agreed")),
            "source": "file",
        }
    except Exception as e:
        return {"agreed": False, "needs_prompt": True, "source": "error", "error": str(e)}


def load_token_status_hook() -> dict:
    """device_token 존재 여부만 확인 — 원문 절대 노출 금지.

    설계서 §6 lifecycle 의 2번 단계. 실제 로드는 후속 공정에서 keyring 연결.
    """
    try:
        from local_agent import token_store as _ts  # type: ignore
        # 존재 여부만 — 원문 절대 안 받음
        present = bool(getattr(_ts, "has_token", lambda: False)())
        return {"present": present, "source": "keyring"}
    except Exception as e:
        return {"present": False, "source": "unavailable", "error": str(e)}


def mask_agent_id(agent_id: str) -> str:
    """agent_id 마스킹 — la-xxx***yyy 형식."""
    if not agent_id or len(agent_id) < 8:
        return "—"
    return f"{agent_id[:6]}***{agent_id[-4:]}"


def role_check_hook(requested_mode: AppMode) -> dict:
    """role 확인 hook — Admin Mode 진입 시 호출.

    설계서 §5 role guard. 실제 role 결정 로직은 후속 공정에서 구현.
    현재는 placeholder — DEFERRED 반환.

    local-only bypass 금지: 127.0.0.1 이어도 role 검사 통과해야 함.
    """
    if requested_mode != AppMode.ADMIN:
        return {"required": False, "passed": True, "role": "any"}

    # placeholder — 실제 구현 시 local_server /api/v1/whoami 호출
    return {
        "required": True,
        "passed": False,
        "role": "deferred",
        "deferred": True,
        "reason": "role_check_implementation_pending",
    }


def start_local_server_hook() -> dict:
    """local_server (8765) 기동 hook. 실제 기동은 후속 공정.

    설계서 §6 lifecycle 의 5번 단계.
    """
    return {"started": False, "deferred": True, "port": 8765,
            "reason": "server_lifecycle_implementation_pending"}


def start_tray_hook() -> dict:
    """시스템 트레이 표시 hook. 실제 트레이는 후속 공정.

    설계서 §6 lifecycle 의 7번 단계.
    """
    return {"started": False, "deferred": True,
            "reason": "tray_implementation_pending"}


def start_admin_webview_hook() -> dict:
    """pywebview 창 lazy load hook. 실제 창은 후속 공정.

    설계서 §6.2.
    """
    return {"started": False, "deferred": True,
            "reason": "admin_webview_implementation_pending"}


def graceful_shutdown_hook() -> dict:
    """종료 hook — local_server / heartbeat / tray 순차 정리.

    설계서 §6.3. 본 공정은 lock 해제만 구현.
    """
    release_lock()
    return {"shutdown": True, "lock_released": True}


# ── diagnostics ──────────────────────────────────────────────────────────

def _redact(s: str) -> str:
    """문자열 내 secret 패턴 redact."""
    if not s:
        return s
    import re
    patterns = [
        (r"(device_token=)[^\s&]+", r"\1[REDACTED]"),
        (r"(registration_code=)[^\s&]+", r"\1[REDACTED]"),
        (r"(token=)[^\s&]+", r"\1[REDACTED]"),
        (r"(bearer\s+)\S+", r"\1[REDACTED]"),
        (r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED_API_KEY]"),
    ]
    for pat, rep in patterns:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    return s


def build_diagnostics(mode: AppMode = AppMode.TRAY) -> dict:
    """진단 정보 dict 생성 — 모든 secret/PII redact 적용.

    HAEHAN_TRAY_REGISTRATION_MERGE_01: server_url / ws_url / agent_id (masked) /
    heartbeat 상태를 tray_runtime 의 통합 source 와 동일하게 노출.
    """
    consent = check_consent_hook()
    token = load_token_status_hook()
    role = role_check_hook(AppMode.ADMIN)
    lock_pid = _read_lock()

    # tray_runtime 의 통합 source 사용 — server_url / agent_id / token_present
    server_url_redacted = ""
    ws_url_redacted = ""
    masked_aid = "—"
    state = "NOT_REGISTERED"
    keyring_backend = ""
    try:
        from desktop import tray_runtime
        status = tray_runtime.check_registration_status()
        payload = tray_runtime.build_diagnostics_payload(
            status=status,
            heartbeat_state="CONNECTED" if status.registered else "NOT_REGISTERED",
        )
        server_url_redacted = payload.get("server_url_redacted", "")
        ws_url_redacted = payload.get("ws_url_redacted", "")
        masked_aid = payload.get("agent_id_masked") or "—"
        state = payload.get("state", state)
        keyring_backend = payload.get("keyring_backend", "")
    except Exception as e:
        logger.debug("diagnostics tray_runtime unavailable: %s", type(e).__name__)

    return {
        "app": "HaehanAI",
        "version": __version__,
        "mode": mode.value,
        "lock": {
            "path": str(lock_path()),
            "current_pid": lock_pid,
            "current_pid_alive": _pid_alive(lock_pid) if lock_pid else False,
        },
        "consent": {
            "agreed": consent.get("agreed"),
            "source": consent.get("source"),
        },
        "token": {
            "present": token.get("present"),
            "source": token.get("source"),
            "keyring_backend": keyring_backend,
            # 원문/해시 노출 금지
        },
        "role": {
            "deferred": role.get("deferred"),
            "reason": role.get("reason"),
        },
        "agent_id_masked": masked_aid,
        "server": {
            "url_redacted": server_url_redacted,
            "ws_url_redacted": ws_url_redacted,
            "planned_port": 8765,
            "started": False,
        },
        "heartbeat": {
            "state": state,
        },
        "admin_mode_available": False,
        "ts": datetime.now().isoformat(),
    }


def print_diagnostics(mode: AppMode = AppMode.TRAY) -> None:
    """진단 정보 stdout 출력 — redact 적용."""
    data = build_diagnostics(mode)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    text = _redact(text)
    print(text)


# ── CLI 파서 ─────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="HaehanAI",
        description="HaehanAI 통합 데스크탑 앱 (단일 exe launcher foundation)",
        add_help=True,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tray", action="store_true",
                       help="Tray Mode (기본 — 일반 사용자)")
    group.add_argument("--admin", action="store_true",
                       help="Admin Mode (관리자/운영자 — role 확인 필요)")
    group.add_argument("--diagnostics", action="store_true",
                       help="진단 정보 stdout 출력 후 종료 (secret 마스킹)")
    group.add_argument("--version", action="store_true",
                       help="버전 출력 후 종료")
    group.add_argument("--reset-lock", action="store_true",
                       help="stale 단일 인스턴스 락 강제 제거")
    return parser


def parse_mode(argv: Optional[list[str]] = None) -> AppMode:
    parser = build_arg_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.version:
        return AppMode.VERSION
    if args.diagnostics:
        return AppMode.DIAGNOSTICS
    if args.reset_lock:
        return AppMode.RESET_LOCK
    if args.admin:
        return AppMode.ADMIN
    # 기본: tray
    return AppMode.TRAY


# ── main 디스패치 ─────────────────────────────────────────────────────────

def run_tray_mode(*, skip_gui: bool = False, role: str = "any") -> int:
    """Tray Mode 진입 — HAEHAN_TRAY_REGISTRATION_MERGE_01 에서 실제 통합.

    foundation hook 들은 backward compat 용으로 유지 (deferred 반환).
    실제 등록/heartbeat/트레이는 desktop.tray_runtime.run_tray_mode_full() 에서.
    """
    logger.info("[mode=tray] starting integrated tray runtime")

    # foundation hook (backward compat — deferred 반환 유지)
    check_consent_hook()
    load_token_status_hook()
    start_local_server_hook()
    start_tray_hook()

    try:
        from desktop import tray_runtime
    except Exception as e:
        logger.error("tray_runtime import 실패: %s", type(e).__name__)
        return 1

    try:
        result = tray_runtime.run_tray_mode_full(
            role=role,
            admin_mode_available=False,  # HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서 True
            skip_gui=skip_gui,
        )
        logger.info("Tray runtime: registered=%s next=%s heartbeat=%s",
                    result.get("registered"),
                    result.get("next_action"),
                    result.get("heartbeat_started"))
        return 0
    except Exception as e:
        import traceback
        logger.error("Tray Mode 실행 오류: %s\n%s",
                     type(e).__name__, traceback.format_exc())
        return 1


def run_tray_mode_diagnostics() -> dict:
    """Tray Mode 의 등록 상태 + heartbeat 계획을 반환 (테스트/진단용).

    실제 GUI 미기동. 본 공정에서 추가된 진입점.
    """
    from desktop import tray_runtime
    status = tray_runtime.check_registration_status()
    next_action = tray_runtime.decide_next_action(status)
    plan = tray_runtime.plan_heartbeat(status)
    return {
        "registered": status.registered,
        "next_action": next_action,
        "heartbeat_plan_can_start": plan.can_start,
        "heartbeat_plan_reason": plan.reason,
    }


def run_admin_mode() -> int:
    """Admin Mode 진입 — role 확인 후 pywebview lazy load (후속)."""
    logger.info("[mode=admin] foundation — hook only")
    role = role_check_hook(AppMode.ADMIN)
    if role.get("deferred"):
        logger.warning("ADMIN_ROLE_CHECK_DEFERRED — role 구현은 후속 공정에서")
    elif not role.get("passed"):
        logger.error("권한 부족 — Admin Mode 진입 불가")
        return 2
    start_local_server_hook()
    start_admin_webview_hook()
    logger.info("Admin Mode hook 완료 — 실제 webview는 HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01 에서 구현")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """단일 exe 통합 진입점."""
    setup_logging()
    mode = parse_mode(argv)

    # --version / --diagnostics / --reset-lock 은 락 없이 즉시 처리
    if mode == AppMode.VERSION:
        print(f"HaehanAI {__version__}")
        return 0

    if mode == AppMode.RESET_LOCK:
        result = reset_lock()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if mode == AppMode.DIAGNOSTICS:
        print_diagnostics(AppMode.DIAGNOSTICS)
        return 0

    # Tray / Admin — 락 획득 필요
    lock = acquire_lock()
    if not lock.acquired:
        logger.error("이미 다른 인스턴스가 실행 중 (PID=%s). --reset-lock 으로 강제 제거 가능.",
                     lock.pid)
        print(f"HaehanAI 가 이미 실행 중입니다 (PID={lock.pid}).", file=sys.stderr)
        return 3

    if lock.stale:
        logger.info("stale lock 자동 정리됨 (이전 PID=%s)", lock.pid)

    # 테스트/CI 환경: HAEHAN_SKIP_GUI=1 → GUI 미기동 모드
    skip_gui = os.environ.get("HAEHAN_SKIP_GUI", "").strip() in ("1", "true", "True")

    try:
        if mode == AppMode.ADMIN:
            return run_admin_mode()
        return run_tray_mode(skip_gui=skip_gui)
    finally:
        graceful_shutdown_hook()


if __name__ == "__main__":
    sys.exit(main())
