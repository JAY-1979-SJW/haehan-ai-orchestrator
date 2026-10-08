"""Small JSON run logger for Hiworks work commands."""

from __future__ import annotations

import json
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import Any

from scripts.hiworks.schemas import DATA_DIR

RUNS_DIR = DATA_DIR / "hiworks_runs"


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_") or "unknown"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _audit_event(
    event_type: str,
    workflow: dict[str, Any],
    record: dict[str, Any],
    *,
    status: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            event_type,
            site="hiworks",
            workflow=str(workflow.get("key") or "unknown"),
            status=status,
            risk=str(workflow.get("risk") or ""),
            message=message,
            artifact_path=str(record.get("artifact_path") or ""),
            metadata={
                "command": workflow.get("command"),
                **(metadata or {}),
            },
        )
    except Exception:  # noqa: BLE001 - 실행 로그 기록용 컨텍스트 매니저 - 예외를 status/error 필드에 기록하는 로깅 목적, 예외를 삼키지 않고 그대로 전파
        pass


@contextmanager
def work_run(workflow: dict[str, Any], args: list[str] | None = None) -> Iterator[dict[str, Any]]:
    key = _safe_name(str(workflow.get("key") or "unknown"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / key
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}.json"
    started_perf = perf_counter()
    record: dict[str, Any] = {
        "workflow_key": workflow.get("key"),
        "workflow_title": workflow.get("title"),
        "risk": workflow.get("risk"),
        "command": workflow.get("command"),
        "args": list(args or []),
        "started_at": _now(),
        "status": "running",
        "artifact_path": str(path),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _audit_event(
        "HIWORKS_WORK_STARTED",
        workflow,
        record,
        status="running",
        message=f"Hiworks workflow started: {key}",
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
            "HIWORKS_WORK_FAILED",
            workflow,
            record,
            status="failed",
            message=f"Hiworks workflow failed: {key}",
            metadata={"error_type": type(exc).__name__, "error": str(exc)},
        )
        raise
    else:
        record["status"] = "ok"
        _audit_event(
            "HIWORKS_WORK_COMPLETED",
            workflow,
            record,
            status="ok",
            message=f"Hiworks workflow completed: {key}",
        )
    finally:
        record["finished_at"] = _now()
        record["elapsed_ms"] = int((perf_counter() - started_perf) * 1000)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Hiworks run log: {path}")
