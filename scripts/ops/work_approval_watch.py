"""Monitor that active work stays inside an approved baseline scope."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "docs" / "baseline" / "WORK_APPROVAL_MONITORING_BASELINE.md"
DEFAULT_LATEST = ROOT / "data" / "runtime" / "work_approval_watch_latest.json"
DEFAULT_HISTORY = ROOT / "data" / "runtime" / "work_approval_watch_history.jsonl"
DEFAULT_RUNTIME_REPORTS = [
    ROOT / "data" / "runtime" / "deploy_api_with_runtime_gates_latest.json",
    ROOT / "data" / "runtime" / "runtime_event_watch_latest.json",
    ROOT / "data" / "runtime" / "orchestrator_boundary_stress_latest.json",
]
DEFAULT_WORK_RECORD = ROOT / "data" / "runtime" / "ai_work_record_latest.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip('"')


def git_changed_paths(*, source: str = "worktree") -> list[str]:
    if source not in {"worktree", "staged"}:
        raise ValueError(f"unsupported_changed_source:{source}")
    command = ["git", "status", "--porcelain=v1", "-z"]
    if source == "staged":
        command = ["git", "diff", "--cached", "--name-only", "-z"]
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git changed-path query failed: {proc.stderr[-300:]}")
    if source == "staged":
        return sorted(normalize_path(entry) for entry in proc.stdout.split("\0") if entry)
    paths = []
    entries = [entry for entry in proc.stdout.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status = entry[:2]
        raw = entry[3:]
        if status[0] == "R" or status[1] == "R":
            if index < len(entries):
                raw = entries[index]
                index += 1
        paths.append(normalize_path(raw))
    return sorted(paths)


def baseline_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "ok": False,
            "status": "baseline_missing",
            "path": str(path),
            "failed_check_ids": ["baseline_missing"],
        }
    text = path.read_text(encoding="utf-8")
    failed = []
    if "Status: LOCKED" not in text:
        failed.append("baseline_not_locked")
    if "Approved by:" not in text:
        failed.append("baseline_missing_approval")
    if "Baseline ID:" not in text:
        failed.append("baseline_missing_id")
    return {
        "ok": not failed,
        "status": "ok" if not failed else "baseline_not_approved",
        "path": str(path),
        "failed_check_ids": failed,
    }


def path_allowed(path: str, scopes: list[str]) -> bool:
    normalized = normalize_path(path)
    for scope in scopes:
        item = normalize_path(scope)
        if item.endswith("/"):
            if normalized.startswith(item):
                return True
        elif normalized == item:
            return True
    return False


def scope_status(paths: list[str], scopes: list[str]) -> dict[str, Any]:
    out_of_scope = [path for path in paths if not path_allowed(path, scopes)]
    return {
        "ok": not out_of_scope,
        "status": "ok" if not out_of_scope else "out_of_scope_changes_detected",
        "approved_scopes": scopes,
        "changed_paths": paths,
        "out_of_scope_paths": out_of_scope,
        "failed_check_ids": [] if not out_of_scope else ["out_of_scope_changes_detected"],
    }


def runtime_report_status(paths: list[Path]) -> dict[str, Any]:
    reports = []
    failed = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ok = payload.get("ok") is True
            status = payload.get("status", "unknown")
        except Exception:
            ok = False
            status = "missing_or_invalid"
        reports.append({"path": str(path), "ok": ok, "status": status})
        if not ok:
            failed.append(str(path))
    return {
        "ok": not failed,
        "status": "ok" if not failed else "runtime_reports_not_ok",
        "reports": reports,
        "failed_check_ids": [] if not failed else ["runtime_reports_not_ok"],
    }


def work_record_status(path: Path, *, lane: str = "") -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "ok": False,
            "status": "missing_or_invalid",
            "path": str(path),
            "failed_check_ids": ["work_record_missing_or_invalid"],
        }
    failed = []
    for key in ["task_id", "request_summary", "approval_status", "status", "resume_next_step"]:
        if not str(payload.get(key, "")).strip():
            failed.append(f"work_record_missing_{key}")
    if payload.get("secret_values_output") is not False:
        failed.append("work_record_secret_values_output_not_false")
    if not isinstance(payload.get("approved_scopes"), list):
        failed.append("work_record_approved_scopes_not_list")
    record_lane = str(payload.get("lane", ""))
    if lane and record_lane and record_lane != lane:
        failed.append("work_record_lane_mismatch")
    return {
        "ok": not failed,
        "status": "ok" if not failed else "work_record_not_resumable",
        "path": str(path),
        "lane": record_lane,
        "task_id": payload.get("task_id", ""),
        "work_status": payload.get("status", ""),
        "updated_at": payload.get("updated_at", ""),
        "resume_next_step": payload.get("resume_next_step", ""),
        "failed_check_ids": failed,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    baseline = baseline_status(Path(args.baseline))
    paths = git_changed_paths(source=args.changed_source)
    scope = scope_status(paths, args.scope)
    runtime = {"ok": True, "status": "skipped", "reports": [], "failed_check_ids": []}
    if args.require_runtime:
        runtime = runtime_report_status([Path(item) for item in args.runtime_report])
    work_record = {"ok": True, "status": "skipped", "failed_check_ids": []}
    if args.require_work_record:
        work_record = work_record_status(Path(args.work_record), lane=args.lane)
    failed = []
    for section in [baseline, scope, runtime, work_record]:
        failed.extend(section.get("failed_check_ids", []))
    return {
        "schema_version": 1,
        "created_at": now(),
        "workflow": "work_approval_watch",
        "lane": args.lane,
        "changed_source": args.changed_source,
        "ok": not failed,
        "status": "ok" if not failed else "work_approval_watch_failed",
        "failed_check_ids": failed,
        "baseline": baseline,
        "scope": scope,
        "runtime": runtime,
        "work_record": work_record,
        "secret_values_output": False,
    }


def write_payload(payload: dict[str, Any], *, latest: Path, history: Path) -> None:
    latest.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def monitor(args: argparse.Namespace) -> int:
    latest = Path(args.latest)
    history = Path(args.history)
    while True:
        try:
            payload = build_payload(args)
        except Exception as exc:
            payload = {
                "schema_version": 1,
                "created_at": now(),
                "workflow": "work_approval_watch",
                "ok": False,
                "status": "watch_failed",
                "failed_check_ids": ["watch_execution_failed"],
                "error_type": type(exc).__name__,
                "error_summary": str(exc)[:500],
                "secret_values_output": False,
            }
        write_payload(payload, latest=latest, history=history)
        print(f"work_approval_watch status={payload['status']} ok={payload['ok']} report={latest}")
        if args.once:
            return 0 if payload["ok"] else 1
        time.sleep(args.interval)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor approved work scope and runtime reports.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--scope", action="append", required=True, help="Approved path prefix or exact file.")
    parser.add_argument("--lane", default="", help="Parallel work lane name.")
    parser.add_argument("--changed-source", choices=["worktree", "staged"], default="worktree")
    parser.add_argument("--require-runtime", action="store_true")
    parser.add_argument("--runtime-report", action="append", default=[str(item) for item in DEFAULT_RUNTIME_REPORTS])
    parser.add_argument("--require-work-record", action="store_true")
    parser.add_argument("--work-record", default=str(DEFAULT_WORK_RECORD))
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return monitor(parse_args(argv or sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
