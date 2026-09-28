"""Create safe AI work records for handoff and resume."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LATEST = ROOT / "data" / "runtime" / "ai_work_record_latest.json"
DEFAULT_HISTORY = ROOT / "data" / "runtime" / "ai_work_record_history.jsonl"
FORBIDDEN_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"access[_-]?token",
        r"refresh[_-]?token",
        r"client[_-]?secret",
        r"authorization:\s*bearer",
        r"password\s*[:=]",
        r"cookie\s*[:=]",
        r"otp\s*[:=]",
    ]
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_text(value: str) -> str:
    text = value.strip()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            raise ValueError("work_record_rejects_secret_shaped_text")
    return text


def safe_list(items: list[str] | None) -> list[str]:
    return [safe_text(item) for item in (items or []) if item.strip()]


def load_latest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def base_record(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": now(),
        "updated_at": now(),
        "workflow": "ai_work_record",
        "lane": safe_text(args.lane),
        "task_id": safe_text(args.task_id),
        "request_summary": safe_text(args.summary),
        "approval_status": safe_text(args.approval_status),
        "status": safe_text(args.status),
        "approved_scopes": safe_list(args.scope),
        "forbidden_scopes": safe_list(args.forbidden_scope),
        "steps": [],
        "decisions": [],
        "touched": [],
        "commands": [],
        "verification": [],
        "reports": [],
        "commits": [],
        "deployments": [],
        "remaining_risks": [],
        "resume_next_step": safe_text(args.next_step),
        "secret_values_output": False,
    }


def append_record(record: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    record = dict(record)
    record["updated_at"] = now()
    record.setdefault("lane", "")
    record.setdefault("forbidden_scopes", [])
    if getattr(args, "lane", None):
        record["lane"] = safe_text(args.lane)
    if args.status:
        record["status"] = safe_text(args.status)
    if args.step:
        record.setdefault("steps", []).append({"at": now(), "summary": safe_text(args.step)})
    if args.decision:
        record.setdefault("decisions", []).append({"at": now(), "summary": safe_text(args.decision)})
    record.setdefault("touched", []).extend(safe_list(args.touched))
    record.setdefault("commands", []).extend(safe_list(args.command))
    record.setdefault("verification", []).extend(safe_list(args.verification))
    record.setdefault("reports", []).extend(safe_list(args.report))
    record.setdefault("commits", []).extend(safe_list(args.commit))
    record.setdefault("deployments", []).extend(safe_list(args.deployment))
    record.setdefault("remaining_risks", []).extend(safe_list(args.risk))
    if args.next_step:
        record["resume_next_step"] = safe_text(args.next_step)
    record["secret_values_output"] = False
    return record


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    failed = []
    for key in ["task_id", "request_summary", "approval_status", "status", "resume_next_step"]:
        if not str(record.get(key, "")).strip():
            failed.append(f"missing_{key}")
    if "lane" not in record:
        failed.append("missing_lane")
    if record.get("secret_values_output") is not False:
        failed.append("secret_values_output_not_false")
    if not isinstance(record.get("approved_scopes"), list):
        failed.append("approved_scopes_not_list")
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(serialized):
            failed.append("secret_shaped_text_detected")
            break
    return {
        "ok": not failed,
        "status": "ok" if not failed else "invalid_work_record",
        "failed_check_ids": failed,
        "task_id": record.get("task_id", ""),
        "work_status": record.get("status", ""),
        "updated_at": record.get("updated_at", ""),
        "resume_next_step": record.get("resume_next_step", ""),
        "secret_values_output": False,
    }


def write_record(record: dict[str, Any], *, latest: Path, history: Path) -> None:
    latest.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write safe AI work records for handoff and resume.")
    sub = parser.add_subparsers(dest="action", required=True)

    start = sub.add_parser("start")
    add_common_paths(start)
    start.add_argument("--task-id", required=True)
    start.add_argument("--summary", required=True)
    start.add_argument("--approval-status", default="approved")
    start.add_argument("--status", default="in_progress")
    start.add_argument("--lane", default="")
    start.add_argument("--scope", action="append", required=True)
    start.add_argument("--forbidden-scope", action="append")
    start.add_argument("--next-step", default="continue approved scoped work")

    append = sub.add_parser("append")
    add_common_paths(append)
    append.add_argument("--status")
    append.add_argument("--lane")
    append.add_argument("--step")
    append.add_argument("--decision")
    append.add_argument("--touched", action="append")
    append.add_argument("--command", action="append")
    append.add_argument("--verification", action="append")
    append.add_argument("--report", action="append")
    append.add_argument("--commit", action="append")
    append.add_argument("--deployment", action="append")
    append.add_argument("--risk", action="append")
    append.add_argument("--next-step")

    complete = sub.add_parser("complete")
    add_common_paths(complete)
    complete.add_argument("--step", default="completed approved work")
    complete.add_argument("--status", default="completed")
    complete.add_argument("--lane")
    complete.add_argument("--decision")
    complete.add_argument("--touched", action="append")
    complete.add_argument("--command", action="append")
    complete.add_argument("--verification", action="append")
    complete.add_argument("--report", action="append")
    complete.add_argument("--commit", action="append")
    complete.add_argument("--deployment", action="append")
    complete.add_argument("--risk", action="append")
    complete.add_argument("--next-step", default="review latest work record before starting new work")

    status = sub.add_parser("status")
    add_common_paths(status)
    status.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    latest = Path(args.latest)
    history = Path(args.history)
    try:
        if args.action == "start":
            record = base_record(args)
            write_record(record, latest=latest, history=history)
            result = validate_record(record)
        elif args.action in {"append", "complete"}:
            current = load_latest(latest)
            if current is None:
                raise RuntimeError("work_record_missing")
            record = append_record(current, args)
            write_record(record, latest=latest, history=history)
            result = validate_record(record)
        else:
            current = load_latest(latest)
            if current is None:
                result = {
                    "ok": False,
                    "status": "work_record_missing",
                    "failed_check_ids": ["work_record_missing"],
                    "secret_values_output": False,
                }
            else:
                result = validate_record(current)
    except Exception as exc:  # noqa: BLE001 - 작업기록(work record) 검증 CLI — 처리 중 예외 발생 시 ok=False, status=work_record_failed 로 실패 판정하는 fail-closed 경로. 예외를 허용 방향으로 흡수하지 않음.
        result = {
            "ok": False,
            "status": "work_record_failed",
            "failed_check_ids": ["work_record_failed"],
            "error_type": type(exc).__name__,
            "error_summary": str(exc)[:300],
            "secret_values_output": False,
        }
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ai_work_record status={result['status']} ok={result['ok']} latest={latest}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
