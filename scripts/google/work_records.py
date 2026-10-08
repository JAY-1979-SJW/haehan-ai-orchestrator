"""Google lane work records for user-visible handoff and resume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.common import ai_work_record, ai_work_session

ROOT = Path(__file__).resolve().parents[2]
LANE = "google"
DEFAULT_RECORD_ROOT = ai_work_session.DEFAULT_RECORD_ROOT
DEFAULT_SCOPES = [
    "scripts/google/",
    "scripts/ops/audit_google_domain_module_boundaries.py",
    "tests/google/test_google_module_check.py",
    "tests/quality_gates/test_module_quality_gate.py",
    "docs/baseline/",
]
DEFAULT_FORBIDDEN_SCOPES = [
    "scripts/naver/",
]


def record_paths(record_root: Path | None = None) -> tuple[Path, Path]:
    return ai_work_session.paths(record_root or DEFAULT_RECORD_ROOT, LANE)


def _namespace(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _load_or_start(
    *,
    latest: Path,
    history: Path,
    task_id: str,
    summary: str,
    next_step: str,
) -> dict[str, Any]:
    current = ai_work_record.load_latest(latest)
    if current and current.get("lane") == LANE and current.get("secret_values_output") is False:
        return current

    args = _namespace(
        lane=LANE,
        task_id=task_id,
        summary=summary,
        approval_status="approved",
        status="in_progress",
        scope=DEFAULT_SCOPES,
        forbidden_scope=DEFAULT_FORBIDDEN_SCOPES,
        next_step=next_step,
    )
    record = ai_work_record.base_record(args)
    ai_work_record.write_record(record, latest=latest, history=history)
    ai_work_session.write_index(latest.parent.parent, LANE, latest)
    return record


def checkpoint(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    *,
    step: str,
    command: str,
    verification: str | None = None,
    report: str | None = None,
    touched: list[str] | None = None,
    status: str = "in_progress",
    next_step: str = "read google lane latest work record before continuing",
    task_id: str = "google-domain-management",
    summary: str = "manage google modules, gates, boundaries, and work records",
    record_root: Path | None = None,
) -> dict[str, Any]:
    latest, history = record_paths(record_root)
    current = _load_or_start(
        latest=latest,
        history=history,
        task_id=task_id,
        summary=summary,
        next_step=next_step,
    )
    args = _namespace(
        lane=LANE,
        status=status,
        step=step,
        decision=None,
        touched=touched or [],
        command=[command],
        verification=[verification] if verification else [],
        report=[report] if report else [],
        commit=[],
        deployment=[],
        risk=[],
        next_step=next_step,
    )
    record = ai_work_record.append_record(current, args)
    ai_work_record.write_record(record, latest=latest, history=history)
    ai_work_session.write_index(latest.parent.parent, LANE, latest)
    return record


def load_latest(record_root: Path | None = None) -> dict[str, Any] | None:
    latest, _ = record_paths(record_root)
    return ai_work_record.load_latest(latest)


def load_history(limit: int = 20, record_root: Path | None = None) -> list[dict[str, Any]]:
    _, history = record_paths(record_root)
    if not history.exists():
        return []
    lines = [line for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines[-max(limit, 1) :]]
    return records
