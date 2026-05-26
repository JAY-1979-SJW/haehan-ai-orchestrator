"""Stress-test the orchestrator Docker boundary without touching other apps."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTAINER = "haehan-ai-orchestrator-api"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8400/api/v1/health"
DEFAULT_REPORT = ROOT / "data" / "runtime" / "orchestrator_boundary_stress_latest.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, timeout: int = 240) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def json_gate(args: list[str], *, name: str, timeout: int = 240) -> dict[str, Any]:
    code, out, err = run(args, timeout=timeout)
    try:
        payload = json.loads(out)
    except Exception:
        payload = {
            "ok": False,
            "status": f"{name}_json_parse_failed",
            "error_summary": (err or out)[-500:],
            "secret_values_output": False,
        }
    ok = code == 0 and (payload.get("ok") is True or payload.get("verdict", {}).get("ok") is True)
    return {
        "name": name,
        "ok": ok,
        "exit_code": code,
        "status": payload.get("status") or payload.get("verdict", {}).get("status"),
        "failed_check_ids": payload.get("failed_check_ids") or payload.get("verdict", {}).get("failed", []),
    }


def health_check(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read(300).decode("utf-8", "replace")
            return {
                "name": "api_health",
                "ok": response.status == 200,
                "status_code": response.status,
                "body_tail": body[-300:],
            }
    except Exception as exc:
        return {
            "name": "api_health",
            "ok": False,
            "status": "api_health_failed",
            "error_summary": str(exc)[:300],
        }


def run_iteration(container: str, health_url: str, iteration: int) -> dict[str, Any]:
    checks = [
        json_gate([
            sys.executable,
            "scripts/ops/verify_compose_project_boundary.py",
            "--json",
        ], name="compose_project_boundary"),
        json_gate([
            sys.executable,
            "scripts/ops/verify_container_orphans.py",
            "--container",
            container,
            "--json",
        ], name="container_orphans"),
        json_gate([
            sys.executable,
            "scripts/ops/verify_runtime_drift.py",
            "--self",
            "--json",
        ], name="runtime_drift"),
        health_check(health_url),
    ]
    return {
        "iteration": iteration,
        "created_at": now(),
        "ok": all(check.get("ok") for check in checks),
        "checks": checks,
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def stress(args: argparse.Namespace) -> dict[str, Any]:
    iterations = []
    for index in range(1, args.iterations + 1):
        iterations.append(run_iteration(args.container, args.health_url, index))
        if index < args.iterations:
            time.sleep(args.delay)
    failed = [item for item in iterations if not item["ok"]]
    return {
        "schema_version": 1,
        "workflow": "orchestrator_boundary_stress",
        "created_at": now(),
        "ok": not failed,
        "status": "ok" if not failed else "stress_failed",
        "iterations": args.iterations,
        "failed_iterations": [item["iteration"] for item in failed],
        "results": iterations,
        "secret_values_output": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stress-test orchestrator Docker boundary gates.")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = stress(args)
    report = Path(args.report)
    write_report(payload, report)
    print(f"orchestrator_boundary_stress status={payload['status']} iterations={args.iterations} report={report}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
