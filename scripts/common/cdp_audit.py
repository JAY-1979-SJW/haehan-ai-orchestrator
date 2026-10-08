"""CDP/세션 감사 로거.

L1 운영, L2 감사, L3 세션 이벤트 분리 저장. JSONL append-only.
민감정보 자동 마스킹.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

KST = timezone(timedelta(hours=9))
AUDIT_ROOT = data_dir() / "audit"
SCHEMA_VERSION = 1

_SENSITIVE_KEYS = re.compile(r"(password|token|auth|secret|apikey|api_key|cookie)", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RRN_RE = re.compile(r"\d{6}-\d{7}")


def _git_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, encoding="utf-8", timeout=2
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 - 감사 레코드용 git commit hash 조회 실패 시 빈 문자열 반환 — 부가 정보 실패, 감사 기록 자체 차단과 무관
        return ""


def _mask_value(v: Any) -> Any:
    if isinstance(v, str):
        v = _EMAIL_RE.sub("***@***", v)
        v = _RRN_RE.sub("******-*******", v)
        return v[:8000]
    if isinstance(v, dict):
        return {k: ("***" if _SENSITIVE_KEYS.search(k) else _mask_value(val)) for k, val in v.items()}
    if isinstance(v, list):
        return [_mask_value(x) for x in v]
    return v


def _path_for(level: str) -> Path:
    today = datetime.now(KST).strftime("%Y%m%d")
    yyyymm = datetime.now(KST).strftime("%Y%m")
    if level == "L1":
        return AUDIT_ROOT / "L1_runtime" / f"browser_runtime_{today}.jsonl"
    if level == "L2":
        return AUDIT_ROOT / "L2_audit" / f"browser_audit_{today}.jsonl"
    if level == "L3":
        return AUDIT_ROOT / "L3_session" / f"session_events_{yyyymm}.jsonl"
    raise ValueError(f"unknown level: {level}")


def emit(level: str, event: str, actor: str, **fields) -> None:
    rec = {
        "ts": datetime.now(KST).isoformat(timespec="milliseconds"),
        "level": level,
        "event": event,
        "actor": actor,
        "session_id": fields.pop("session_id", None) or str(uuid.uuid4()),
        "user": os.environ.get("USERNAME") or os.environ.get("USER", ""),
        "host_pid": os.getpid(),
        "git_sha": _git_sha(),
        "schema_version": SCHEMA_VERSION,
        **_mask_value(fields),
    }
    p = _path_for(level)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def L1(event: str, actor: str, **fields):
    emit("L1", event, actor, **fields)


def L2(event: str, actor: str, **fields):
    emit("L2", event, actor, **fields)


def L3(event: str, actor: str, **fields):
    emit("L3", event, actor, **fields)


def rotate(retention_days: dict[str, int] | None = None) -> dict:
    retention_days = retention_days or {"L1_runtime": 30, "L2_audit": 365, "L3_session": 365}
    deleted = {}
    for sub, days in retention_days.items():
        d = AUDIT_ROOT / sub
        if not d.exists():
            continue
        cutoff = datetime.now(KST) - timedelta(days=days)
        n = 0
        for f in d.glob("*.jsonl"):
            if datetime.fromtimestamp(f.stat().st_mtime, KST) < cutoff:
                f.unlink()
                n += 1
        deleted[sub] = n
    return deleted
