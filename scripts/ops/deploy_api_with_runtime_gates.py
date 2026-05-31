"""Deploy the API container with mandatory runtime integrity gates.

This script is intended to replace ad-hoc `docker compose up -d --build`
for the API service. It is intentionally narrow: one server repo path, one
compose service, and read-only verification before and after the live change.
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
DEFAULT_SERVICE = "ai-orchestrator-api"
DEFAULT_CONTAINER = "haehan-ai-orchestrator-api"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8400/api/v1/health"
DEFAULT_REPORT = ROOT / "data" / "runtime" / "deploy_api_with_runtime_gates_latest.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, timeout: int = 300, cwd: str | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=cwd or str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def must(args: list[str], *, step: str, timeout: int = 300, cwd: str | None = None) -> dict[str, Any]:
    code, out, err = run(args, timeout=timeout, cwd=cwd)
    result = {
        "step": step,
        "command": " ".join(args),
        "ok": code == 0,
        "exit_code": code,
        "stdout_tail": out[-1200:],
        "stderr_tail": err[-1200:],
    }
    if code != 0:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def git_status_clean() -> bool:
    code, out, _ = run(["git", "status", "--short"], timeout=60)
    return code == 0 and out == ""


def wait_health(url: str, *, attempts: int, delay: float) -> dict[str, Any]:
    last = ""
    for attempt in range(1, attempts + 1):
        code, out, err = run([
            sys.executable,
            "-c",
            (
                "import sys, urllib.request; "
                f"url={url!r}; "
                "resp=urllib.request.urlopen(url, timeout=3); "
                "body=resp.read().decode('utf-8', 'replace'); "
                "print(resp.status); print(body[:400]); "
                "sys.exit(0 if resp.status == 200 else 1)"
            ),
        ], timeout=10)
        last = out or err
        if code == 0:
            return {"step": "health_check", "ok": True, "attempt": attempt, "output": last[-500:]}
        time.sleep(delay)
    raise RuntimeError(json.dumps({
        "step": "health_check",
        "ok": False,
        "attempts": attempts,
        "last_output": last[-500:],
    }, ensure_ascii=False))


def wait_container_healthy(container: str, *, attempts: int, delay: float) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        code, out, err = run(["docker", "inspect", container], timeout=30)
        if code == 0:
            data = json.loads(out)[0]
            state = data.get("State", {})
            last = {
                "status": state.get("Status", ""),
                "health": state.get("Health", {}).get("Status", ""),
                "restart_count": data.get("RestartCount", 0),
            }
            if last["status"] == "running" and last["health"] in {"", "healthy"}:
                return {"step": "container_health", "ok": True, "attempt": attempt, "state": last}
        else:
            last = {"status": "inspect_failed", "stderr_tail": err[-500:]}
        time.sleep(delay)
    raise RuntimeError(json.dumps({
        "step": "container_health",
        "ok": False,
        "attempts": attempts,
        "last_state": last,
    }, ensure_ascii=False))


def payload_ok(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is True:
        return True
    verdict = payload.get("verdict")
    return isinstance(verdict, dict) and verdict.get("ok") is True


def run_json_command(args: list[str], *, step: str, timeout: int = 240, cwd: str | None = None) -> dict[str, Any]:
    code, out, err = run(args, timeout=timeout, cwd=cwd)
    try:
        payload = json.loads(out)
    except Exception:
        payload = {
            "ok": False,
            "status": f"{step}_failed_to_parse_json",
            "error_summary": (err or out)[-500:],
            "secret_values_output": False,
        }
    if code != 0 or not payload_ok(payload):
        raise RuntimeError(json.dumps({
            "step": step,
            "ok": False,
            "exit_code": code,
            "payload": payload,
            "stderr_tail": err[-500:],
        }, ensure_ascii=False))
    return {"step": step, "ok": True, "payload": payload}


def deploy(args: argparse.Namespace) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    compose_dir = str(Path(args.compose_dir).resolve()) if args.compose_dir else str(ROOT)
    if not args.approved:
        raise RuntimeError("deployment_requires_--approved")
    if not git_status_clean():
        raise RuntimeError("server_worktree_must_be_clean_before_deploy")
    steps.append(must(["git", "fetch", args.remote, args.branch], step="git_fetch", timeout=120))
    steps.append(must(["git", "pull", "--ff-only", args.remote, args.branch], step="git_pull_ff_only", timeout=180))
    if not git_status_clean():
        raise RuntimeError("server_worktree_must_be_clean_after_pull")
    steps.append(must([sys.executable, "scripts/ops/verify_docker_context_policy.py"], step="docker_context_policy", timeout=120))
    verify_boundary_cmd = [sys.executable, "scripts/ops/verify_compose_project_boundary.py", "--json"]
    if args.compose_dir:
        verify_boundary_cmd += ["--compose-dir", compose_dir]
    steps.append(run_json_command(verify_boundary_cmd, step="compose_project_boundary", timeout=120))
    steps.append(must(["docker", "compose", "build", args.service], step="docker_compose_build", timeout=900, cwd=compose_dir))
    steps.append(must(["docker", "compose", "up", "-d", "--no-deps", args.service], step="docker_compose_up", timeout=300, cwd=compose_dir))
    steps.append(wait_health(args.health_url, attempts=args.health_attempts, delay=args.health_delay))
    steps.append(wait_container_healthy(args.container, attempts=args.health_attempts, delay=args.health_delay))
    steps.append(run_json_command([
        sys.executable,
        "scripts/ops/verify_container_orphans.py",
        "--container",
        args.container,
        "--json",
    ], step="container_orphans", timeout=240))
    steps.append(run_json_command([
        sys.executable,
        "scripts/ops/verify_runtime_drift.py",
        "--self",
        "--json",
    ], step="runtime_drift", timeout=240))
    return {
        "schema_version": 1,
        "created_at": now(),
        "workflow": "deploy_api_with_runtime_gates",
        "ok": True,
        "status": "ok",
        "service": args.service,
        "container": args.container,
        "steps": steps,
        "secret_values_output": False,
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy API with mandatory runtime integrity gates.")
    parser.add_argument("--approved", action="store_true", help="Required live deployment approval flag.")
    parser.add_argument("--compose-dir", default=None, help="Directory containing docker-compose.yml (defaults to repo root).")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="master")
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--health-attempts", type=int, default=20)
    parser.add_argument("--health-delay", type=float, default=3.0)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report_path = Path(args.report)
    try:
        payload = deploy(args)
    except Exception as exc:
        error_payload = None
        try:
            error_payload = json.loads(str(exc))
        except Exception:
            pass
        payload = {
            "schema_version": 1,
            "created_at": now(),
            "workflow": "deploy_api_with_runtime_gates",
            "ok": False,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error_summary": str(exc)[:1000],
            "error_payload": error_payload,
            "secret_values_output": False,
        }
        write_report(payload, report_path)
        print(f"deploy_api_with_runtime_gates status=failed report={report_path}")
        return 1
    write_report(payload, report_path)
    print(f"deploy_api_with_runtime_gates status=ok report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
