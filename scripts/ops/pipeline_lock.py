# module_category: audit
# primary_trade: common
"""파이프라인 전역 락 — verify/merge 동시 실행 차단(기준서 §5.2).

락 파일: <메인저장소>/data/ops/locks/{name}.lock (worktree 에서도 git common-dir 로 메인 루트를 찾음).
이미 살아 있는 락이면 LockBusy(exit 4 상당). 죽은 락은 stale 복구(잔여 verify_base_* worktree 정리).
재진입: 환경변수 PIPELINE_LOCK_TOKEN 이 락 token 과 같으면 공유.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

TOKEN_ENV = "PIPELINE_LOCK_TOKEN"
EXIT_BUSY = 4


class LockBusy(RuntimeError):
    pass


def main_root(start: Path | None = None) -> Path:
    cwd = start or Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return Path(out).parent
    except Exception:
        return cwd


def lock_path(name: str, root: Path | None = None) -> Path:
    return (root or main_root()) / "data" / "ops" / "locks" / f"{name}.lock"


def log_dir(root: Path | None = None) -> Path:
    return (root or main_root()) / "data" / "ops" / "logs"


def _create_time(pid: int) -> int | None:
    """프로세스 생성시각(정수). 죽었으면 None. Windows=ctypes, POSIX=/proc 또는 kill."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        k = ctypes.windll.kernel32  # type: ignore[attr-defined]
        k.OpenProcess.restype = wintypes.HANDLE
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
            if not k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
                return None
            code = wintypes.DWORD()
            if k.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != 259:  # STILL_ACTIVE
                return None
            return (c.dwHighDateTime << 32) | c.dwLowDateTime
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
    except Exception:
        return 0


def read_lock(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_alive(info: dict) -> bool:
    ct = _create_time(int(info.get("pid", 0)))
    return ct is not None and ct == info.get("proc_create_time")


def describe(info: dict) -> str:
    mins = int((time.time() - info.get("started_ts", time.time())) / 60)
    return (
        f"이미 실행 중 (pid {info.get('pid')}, 시작 {mins}분 전). 로그: {info.get('log_path')}. "
        "재실행 금지 — 로그 tail 로 진행 확인"
    )


def _cleanup_stale(info: dict, root: Path) -> None:
    tmp = info.get("tmp_dir")
    if tmp:
        for sub in ("base", "head"):
            subprocess.run(
                ["git", "-C", str(root), "worktree", "remove", "--force", str(Path(tmp) / sub)],
                capture_output=True,
            )
    subprocess.run(["git", "-C", str(root), "worktree", "prune"], capture_output=True)


def acquire(
    name: str, *, cmd: str = "", head: str = "", log_path: str = "", tmp_dir: str = "", root: Path | None = None
) -> str:
    """락 획득 후 token 반환. 살아 있는 락이면 LockBusy. 토큰 일치 시 재진입(해제 책임 없음)."""
    root = root or main_root()
    p = lock_path(name, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        info = {
            "pid": os.getpid(),
            "proc_create_time": _create_time(os.getpid()),
            "started_ts": time.time(),
            "cmd": cmd or " ".join(sys.argv),
            "head": head,
            "log_path": log_path,
            "tmp_dir": tmp_dir,
            "token": uuid.uuid4().hex,
        }
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            cur = read_lock(p)
            if cur and os.environ.get(TOKEN_ENV) == cur.get("token"):
                return cur["token"]
            if cur and is_alive(cur):
                raise LockBusy(describe(cur)) from None
            if cur:
                print(f"[lock] stale 락 복구(pid {cur.get('pid')} 죽음) — 잔여 worktree 정리", file=sys.stderr)
                _cleanup_stale(cur, root)
            with contextlib.suppress(FileNotFoundError):
                p.unlink()
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
        atexit.register(release, name, info["token"], root)
        return info["token"]
    raise LockBusy(f"락 획득 실패: {p}")


def release(name: str, token: str, root: Path | None = None) -> None:
    p = lock_path(name, root)
    cur = read_lock(p)
    if cur and cur.get("token") == token:
        with contextlib.suppress(OSError):
            p.unlink()


def live_lock(name: str, root: Path | None = None) -> dict | None:
    """살아 있는 락 정보(없거나 stale 이면 None) — 훅용 읽기 전용."""
    cur = read_lock(lock_path(name, root))
    return cur if cur and is_alive(cur) else None
