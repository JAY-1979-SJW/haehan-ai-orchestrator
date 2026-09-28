"""Lane-based AI work session helper.

This wraps ai_work_record.py with deterministic per-lane paths so each work
stream can be closed and resumed without mixing records.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_ROOT = ROOT / "data" / "runtime" / "ai_work_records"
AI_WORK_RECORD = ROOT / "scripts" / "ops" / "ai_work_record.py"


def safe_lane(value: str) -> str:
    lane = value.strip().replace("\\", "/").strip("/")
    if not lane:
        raise ValueError("lane_required")
    if "/" in lane or ".." in lane or any(ch in lane for ch in '<>:"|?*'):
        raise ValueError("invalid_lane")
    return lane


def paths(record_root: Path, lane: str) -> tuple[Path, Path]:
    lane_dir = record_root / safe_lane(lane)
    return lane_dir / "latest.json", lane_dir / "history.jsonl"


def run_record(args: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, str(AI_WORK_RECORD), *args],
        cwd=ROOT,
        text=True,
        check=False,
        encoding="utf-8",
    )
    return proc.returncode


def write_index(record_root: Path, lane: str, latest: Path) -> None:
    index = record_root / "latest_lane.json"
    try:
        latest_path = str(latest.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        latest_path = str(latest)
    payload = {
        "schema_version": 1,
        "lane": lane,
        "latest": latest_path,
        "secret_values_output": False,
    }
    record_root.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start, checkpoint, close, and resume-check AI work sessions.")
    parser.add_argument("--record-root", default=str(DEFAULT_RECORD_ROOT))
    parser.add_argument("--lane", required=True)
    sub = parser.add_subparsers(dest="action", required=True)

    start = sub.add_parser("start")
    start.add_argument("--task-id", required=True)
    start.add_argument("--summary", required=True)
    start.add_argument("--scope", action="append", required=True)
    start.add_argument("--forbidden-scope", action="append")
    start.add_argument("--approval-status", default="approved")
    start.add_argument("--next-step", default="continue approved scoped work")

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--step")
    checkpoint.add_argument("--decision")
    checkpoint.add_argument("--touched", action="append")
    checkpoint.add_argument("--command", action="append")
    checkpoint.add_argument("--verification", action="append")
    checkpoint.add_argument("--report", action="append")
    checkpoint.add_argument("--risk", action="append")
    checkpoint.add_argument("--next-step")
    checkpoint.add_argument("--status", default="in_progress")

    close = sub.add_parser("close")
    close.add_argument("--step", default="closed current work session")
    close.add_argument("--decision")
    close.add_argument("--touched", action="append")
    close.add_argument("--command", action="append")
    close.add_argument("--verification", action="append")
    close.add_argument("--report", action="append")
    close.add_argument("--risk", action="append")
    close.add_argument("--next-step", default="read latest work session before starting new work")
    close.add_argument("--status", default="completed")

    resume = sub.add_parser("resume-check")
    resume.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


def append_many(out: list[str], flag: str, values: list[str] | None) -> None:
    for value in values or []:
        out.extend([flag, value])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    record_root = Path(args.record_root)
    latest, history = paths(record_root, args.lane)
    common = ["--latest", str(latest), "--history", str(history)]

    if args.action == "start":
        command = [
            "start",
            *common,
            "--task-id",
            args.task_id,
            "--summary",
            args.summary,
            "--approval-status",
            args.approval_status,
            "--lane",
            args.lane,
            "--next-step",
            args.next_step,
        ]
        append_many(command, "--scope", args.scope)
        append_many(command, "--forbidden-scope", args.forbidden_scope)
        code = run_record(command)
        if code == 0:
            write_index(record_root, args.lane, latest)
        return code

    if args.action == "resume-check":
        command = ["status", *common]
        if args.json:
            command.append("--json")
        return run_record(command)

    action = "complete" if args.action == "close" else "append"
    command = [action, *common, "--lane", args.lane, "--status", args.status]
    for flag, attr in [
        ("--step", "step"),
        ("--decision", "decision"),
        ("--next-step", "next_step"),
    ]:
        value = getattr(args, attr, None)
        if value:
            command.extend([flag, value])
    append_many(command, "--touched", getattr(args, "touched", None))
    append_many(command, "--command", getattr(args, "command", None))
    append_many(command, "--verification", getattr(args, "verification", None))
    append_many(command, "--report", getattr(args, "report", None))
    append_many(command, "--risk", getattr(args, "risk", None))
    code = run_record(command)
    if code == 0:
        write_index(record_root, args.lane, latest)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
