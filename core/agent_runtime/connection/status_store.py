"""Local Agent 상태 파일 읽기/쓰기.

data/local_agent/status.json에 실행 상태를 기록한다.
secret/session/cookie/token/password 값 절대 기록 금지.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.paths import repo_root

# 이동해도·실행 위치가 바뀌어도 값이 안 바뀌게 작업 디렉터리 상대 대신 repo_root() 기준으로
# 고정(T4 C1과 같은 원칙). 실제 쓰이는 값(repo 안 data/local_agent)은 그대로 유지 — OS 표준
# 데이터 폴더(data_dir())로의 전환은 범위 밖(T4 D4 각주, 별도 후속 커밋).
_STATUS_DIR = repo_root() / "data" / "local_agent"
_STATUS_FILE = _STATUS_DIR / "status.json"
_LOCK_FILE = _STATUS_DIR / "agent.lock"

# tools/gates/gate_core.py의 _opt_out_guard()와 같은 원자적 잠금 처리(T4 C2).
_IS_WINDOWS = os.name == "nt"

# 기록 금지 키 목록
_FORBIDDEN_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pw",
        "session",
        "cookie",
        "token",
        "access_token",
        "refresh_token",
        "otp",
        "cert_password",
    }
)


def _ensure_dir() -> None:
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _write_atomic(path: Path, text: str) -> None:
    """임시 파일에 쓴 뒤 교체 — 쓰는 중 죽어도 반쪽 파일이 남지 않는다(T4 C2)."""
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """기록 금지 키 제거."""
    return {k: v for k, v in data.items() if k.lower() not in _FORBIDDEN_KEYS}


# ── 상태 파일 ──────────────────────────────────────────────────────────


def write_status(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    running: bool,
    task_id: str = "",
    domain: str = "",
    action: str = "",
    approved_scope: list[str] | None = None,
    idle_timeout_s: int = 1800,
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    _ensure_dir()
    payload: dict[str, Any] = {
        "running": running,
        "task_id": task_id,
        "domain": domain,
        "action": action,
        "approved_scope": approved_scope or [],
        "idle_timeout_s": idle_timeout_s,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if reason:
        payload["stop_reason"] = reason
    if extra:
        payload.update(_sanitize(extra))
    _write_atomic(_STATUS_FILE, json.dumps(payload, ensure_ascii=False, indent=2))


def read_status() -> dict[str, Any]:
    if not _STATUS_FILE.exists():
        return {"running": False}
    try:
        data = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
        return _sanitize(data)
    except Exception:  # noqa: BLE001 - 상태/락 파일 읽기 실패시 안전한 기본값(running:False, 빈 문자열) 반환 — 쓰기 없는 읽기전용 상태조회
        return {"running": False, "error": "status file unreadable"}


# ── lock 파일 ──────────────────────────────────────────────────────────


def acquire_lock(task_id: str) -> bool:
    """Lock 획득. 이미 lock 존재 시 False 반환.

    기존에는 exists() 확인 후 write_text()로 거는 check-then-set이라 두 프로세스가
    동시에 호출하면 둘 다 성공할 수 있었다(T4 R10) — os.open(O_CREAT|O_EXCL)로
    원자적으로 바꾼다(tools/gates/gate_core.py의 _opt_out_guard()와 같은
    패턴). 재시도는 하지 않는다 — 기존처럼 한 번 시도해 실패하면 바로 False(동작 범위
    확장 안 함).
    """
    _ensure_dir()
    try:
        fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except PermissionError:
        # Windows: 다른 프로세스가 방금 unlink 한 잠금 파일은 '삭제 보류' 상태라 같은
        # 이름의 생성이 FileExistsError 가 아니라 PermissionError 로 실패한다 — 잠금 중과
        # 같은 뜻으로 처리(tools/gates/gate_core.py와 동일 처리).
        if _IS_WINDOWS:
            return False
        raise
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(task_id)
    return True


def release_lock() -> None:
    if _LOCK_FILE.exists():
        _LOCK_FILE.unlink()


def lock_exists() -> bool:
    return _LOCK_FILE.exists()


def lock_task_id() -> str:
    if not _LOCK_FILE.exists():
        return ""
    try:
        return _LOCK_FILE.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001 - 상태/락 파일 읽기 실패시 안전한 기본값(running:False, 빈 문자열) 반환 — 쓰기 없는 읽기전용 상태조회
        return ""
