"""Docker event-driven runtime integrity watcher.

The watcher subscribes to Docker events for the API container and immediately
runs read-only runtime drift and container orphan checks after relevant events.
It complements the cron-based runtime_drift_watch fallback.
"""
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
DEFAULT_CONTAINER = "haehan-ai-orchestrator-api"
DEFAULT_LATEST = ROOT / "data" / "runtime" / "runtime_event_watch_latest.json"
DEFAULT_HISTORY = ROOT / "data" / "runtime" / "runtime_event_watch_history.jsonl"
RELEVANT_EVENTS = {
    "start",
    "restart",
    "die",
    "stop",
    "destroy",
    "health_status: healthy",
    "health_status: unhealthy",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, cwd: Path = ROOT, timeout: int = 240) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def load_json_output(out: str) -> dict[str, Any]:
    return json.loads(out)


def run_checks(container: str) -> dict[str, Any]:
    drift_latest = ROOT / "data" / "runtime" / "runtime_drift_latest.json"
    drift_history = ROOT / "data" / "runtime" / "runtime_drift_history.jsonl"
    drift_code, drift_out, drift_err = run([
        sys.executable,
        "scripts/ops/runtime_drift_watch.py",
        "--self",
        "--latest",
        str(drift_latest),
        "--history",
        str(drift_history),
        "--exit-zero",
    ])
    orphan_code, orphan_out, orphan_err = run([
        sys.executable,
        "scripts/ops/verify_container_orphans.py",
        "--container",
        container,
        "--json",
    ])
    try:
        orphan_payload: dict[str, Any] = load_json_output(orphan_out)
    except Exception:
        orphan_payload = {
            "ok": False,
            "status": "container_orphan_check_failed",
            "failed_check_ids": ["container_orphan_check_failed"],
            "error_summary": (orphan_err or orphan_out)[:300],
            "secret_values_output": False,
        }
    try:
        drift_payload = json.loads(drift_latest.read_text(encoding="utf-8"))
    except Exception:
        drift_payload = {
            "ok": False,
            "status": "runtime_drift_check_failed",
            "failed_check_ids": ["runtime_drift_check_failed"],
            "error_summary": (drift_err or drift_out)[:300],
            "secret_values_output": False,
        }
    ok = bool(drift_payload.get("ok")) and bool(orphan_payload.get("ok")) and drift_code == 0
    return {
        "schema_version": 1,
        "created_at": now(),
        "workflow": "runtime_event_watch",
        "ok": ok,
        "status": "ok" if ok else "event_check_failed",
        "container": container,
        "drift": {
            "status": drift_payload.get("status"),
            "ok": drift_payload.get("ok"),
            "failed_check_ids": drift_payload.get("failed_check_ids", []),
        },
        "orphans": {
            "status": orphan_payload.get("status"),
            "ok": orphan_payload.get("ok"),
            "failed_check_ids": orphan_payload.get("failed_check_ids", []),
            "untracked_in_container_count": orphan_payload.get("untracked_in_container_count"),
        },
        "secret_values_output": False,
    }


def write_payload(payload: dict[str, Any], *, latest: Path, history: Path) -> None:
    latest.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def parse_event(line: str) -> dict[str, Any]:
    try:
        return json.loads(line)
    except Exception:
        return {"raw": line}


def event_action(event: dict[str, Any]) -> str:
    action = str(event.get("Action") or "")
    status = str(event.get("status") or "")
    return action or status


def watch(args: argparse.Namespace) -> int:
    first = run_checks(args.container)
    first["trigger"] = "startup"
    write_payload(first, latest=Path(args.latest), history=Path(args.history))
    if args.once:
        print(f"runtime_event_watch status={first['status']} ok={first['ok']} trigger=startup")
        return 0 if first["ok"] else 1

    command = [
        "docker",
        "events",
        "--format",
        "{{json .}}",
        "--filter",
        f"container={args.container}",
    ]
    proc = subprocess.Popen(command, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    last_run = 0.0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            event = parse_event(line.strip())
            action = event_action(event)
            if action not in RELEVANT_EVENTS:
                continue
            elapsed = time.monotonic() - last_run
            if elapsed < args.debounce_seconds:
                continue
            last_run = time.monotonic()
            time.sleep(args.settle_seconds)
            payload = run_checks(args.container)
            payload["trigger"] = action
            payload["event"] = {
                "action": action,
                "type": event.get("Type", ""),
                "time": event.get("time", ""),
            }
            write_payload(payload, latest=Path(args.latest), history=Path(args.history))
            print(f"runtime_event_watch status={payload['status']} ok={payload['ok']} trigger={action}", flush=True)
    finally:
        proc.terminate()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Docker events and run runtime integrity checks.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--debounce-seconds", type=float, default=10.0)
    parser.add_argument("--settle-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return watch(parse_args(argv or sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
