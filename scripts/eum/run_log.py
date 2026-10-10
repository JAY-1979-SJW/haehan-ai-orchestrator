"""Small JSON run logger for EUM work commands."""

from __future__ import annotations

import json
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()
RUNS_DIR = ROOT / "data" / "eum_runs"


def _audit_event(
    event_type: str,
    workflow: dict[str, Any],
    record: dict[str, Any],
    *,
    status: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort realtime audit logging for EUM workflows."""
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            event_type,
            site="eum",
            workflow=str(workflow.get("key") or "unknown"),
            status=status,
            risk=str(workflow.get("risk") or ""),
            message=message,
            artifact_path=str(record.get("artifact_path") or ""),
            metadata={
                "code": workflow.get("code"),
                "command": workflow.get("command"),
                **(metadata or {}),
            },
        )
    except Exception:  # noqa: BLE001 - _audit_event: 주석에 명시된 대로 best-effort 실시간 감사로그 전송 - 실패해도 무시하고 계속(로깅 실패가 본작업에 영향 없음)
        pass


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_") or "unknown"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def work_run(workflow: dict[str, Any], args: list[str] | None = None) -> Iterator[dict[str, Any]]:
    """Record a work command execution as a JSON file.

    The logger captures command-level success/failure. Individual work modules
    can still write their own detailed artifacts separately.
    """
    key = _safe_name(str(workflow.get("key") or "unknown"))
    started = _now()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / key
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}.json"
    started_perf = perf_counter()

    record: dict[str, Any] = {
        "workflow_key": workflow.get("key"),
        "workflow_title": workflow.get("title"),
        "risk": workflow.get("risk"),
        "code": workflow.get("code"),
        "command": workflow.get("command"),
        "args": list(args or []),
        "started_at": started,
        "status": "running",
        "artifact_path": str(path),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _audit_event(
        "EUM_WORK_STARTED",
        workflow,
        record,
        status="running",
        message=f"EUM workflow started: {key}",
        metadata={"args": list(args or [])},
    )

    try:
        yield record
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=20),
        }
        _audit_event(
            "EUM_WORK_FAILED",
            workflow,
            record,
            status="failed",
            message=f"EUM workflow failed: {key}",
            metadata={"error_type": type(exc).__name__, "error": str(exc)},
        )
        raise
    else:
        record["status"] = "ok"
        _audit_event(
            "EUM_WORK_COMPLETED",
            workflow,
            record,
            status="ok",
            message=f"EUM workflow completed: {key}",
        )
    finally:
        record["finished_at"] = _now()
        record["elapsed_ms"] = int((perf_counter() - started_perf) * 1000)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EUM run log: {path}")
