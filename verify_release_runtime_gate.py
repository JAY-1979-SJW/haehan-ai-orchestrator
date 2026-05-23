from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"

FORBIDDEN_COMMAND_TOKENS = (
    "docker",
    "docker-compose",
    "electron-builder",
    "git add",
    "git commit",
    "git push",
    "npm run build",
    "next build",
    "pyinstaller",
)

TRANSIENT_MARKERS = (
    "ConnectionRefusedError",
    "TimeoutError",
    "AUTH_TIMEOUT",
    "URLError",
    "PERMISSION_DENIED",
    "PermissionError",
    "WinError 10061",
)


@dataclass(frozen=True)
class GateCheck:
    name: str
    command: tuple[str, ...]
    timeout: int
    classifier: Callable[[str, int], tuple[str, str]]


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    status: str
    detail: str
    attempts: int


def redact(text: str) -> str:
    rules = (
        (re.compile(r"(?i)(Authorization\s*[:=]\s*Bearer\s+)[^\s'\";,]+"), r"\1<redacted>"),
        (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
        (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "sk-<redacted>"),
        (
            re.compile(
                r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
                r"device[_-]?token|secret|password)\s*[:=]\s*)[^\s'\";,]+"
            ),
            r"\1<redacted>",
        ),
    )
    redacted = text
    for pattern, replacement in rules:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def command_text(command: tuple[str, ...]) -> str:
    return " ".join(str(part) for part in command)


def command_is_forbidden(command: tuple[str, ...]) -> bool:
    lowered = command_text(command).lower()
    return any(token in lowered for token in FORBIDDEN_COMMAND_TOKENS)


def has_transient_marker(output: str) -> bool:
    return any(marker in output for marker in TRANSIENT_MARKERS)


def _result_code(output: str) -> str:
    match = re.search(r"RESULT=([A-Z0-9_]+)", output)
    return match.group(1) if match else ""


def _warn_lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip().startswith("[WARN]")]


def classify_local_runtime_live(output: str, returncode: int) -> tuple[str, str]:
    result = _result_code(output)
    if "[FAIL]" in output or result.startswith("FAIL"):
        return "FAIL", result or f"exit_code={returncode}"
    warn_lines = _warn_lines(output)
    blocking_warns = [
        line for line in warn_lines
        if not (
            "desktop exe - not found" in line
            or "desktop shortcut" in line
        )
    ]
    if blocking_warns:
        return "FAIL", "blocking runtime warning: " + "; ".join(blocking_warns[:3])
    if result in {"PASS_LOCAL_RUNTIME_DRY_RUN", "WARN_LOCAL_RUNTIME_DRY_RUN"}:
        return ("WARN" if warn_lines else "PASS"), result or "runtime live completed"
    return "FAIL", result or f"exit_code={returncode}"


def classify_agent_ws_auth(output: str, returncode: int) -> tuple[str, str]:
    if "RESULT=PASS_AGENT_WS_AUTH" in output:
        return "PASS", "AUTH_OK"
    status = next((line.split("=", 1)[1] for line in output.splitlines() if line.startswith("ws_auth_status=")), "")
    return "FAIL", status or f"exit_code={returncode}"


def classify_live_agent_smoke(output: str, returncode: int) -> tuple[str, str]:
    if "[FAIL]" in output or "RESULT=FAIL_LIVE_AGENT_SMOKE" in output:
        return "FAIL", _result_code(output) or f"exit_code={returncode}"
    warn_lines = _warn_lines(output)
    blocking_warns = [line for line in warn_lines if "task dispatch - skipped" not in line]
    if blocking_warns:
        return "FAIL", "blocking live smoke warning: " + "; ".join(blocking_warns[:3])
    if "RESULT=PASS_LIVE_AGENT_SMOKE" in output:
        return "PASS", "server health, agent-ai health, websocket heartbeat passed"
    if "RESULT=WARN_LIVE_AGENT_SMOKE" in output:
        return "WARN", "task dispatch is verified by dedicated check"
    return "FAIL", _result_code(output) or f"exit_code={returncode}"


def classify_live_task_dispatch(output: str, returncode: int) -> tuple[str, str]:
    if "RESULT=PASS_LIVE_TASK_DISPATCH" in output:
        return "PASS", "ws_noop task completed"
    return "FAIL", _result_code(output) or f"exit_code={returncode}"


def classify_pytest_requires_pass(output: str, returncode: int) -> tuple[str, str]:
    if returncode != 0 or " failed" in output:
        return "FAIL", f"exit_code={returncode}"
    match = re.search(r"(\d+) passed", output)
    if match and int(match.group(1)) > 0:
        skipped = re.search(r"(\d+) skipped", output)
        suffix = f", skipped={skipped.group(1)}" if skipped else ""
        return "PASS", f"passed={match.group(1)}{suffix}"
    return "FAIL", "no passed tests observed"


def make_checks(server_url: str) -> tuple[GateCheck, ...]:
    py = sys.executable
    return (
        GateCheck(
            "local_runtime_live",
            (py, "verify_local_runtime_dry_run.py", "--live-server"),
            120,
            classify_local_runtime_live,
        ),
        GateCheck(
            "agent_ws_auth",
            (py, "verify_agent_ws_auth.py", "--server", server_url, "--timeout", "15"),
            60,
            classify_agent_ws_auth,
        ),
        GateCheck(
            "live_agent_smoke",
            (py, "verify_live_agent_smoke.py", "--server", server_url, "--timeout", "15"),
            90,
            classify_live_agent_smoke,
        ),
        GateCheck(
            "live_task_dispatch",
            (py, "verify_live_task_dispatch.py", "--server", server_url, "--timeout", "70"),
            120,
            classify_live_task_dispatch,
        ),
        GateCheck(
            "playwright_bootstrap",
            (py, "-m", "pytest", "tests/test_local_playwright_bootstrap_20260508.py", "-q"),
            120,
            classify_pytest_requires_pass,
        ),
        GateCheck(
            "playwright_smoke",
            (py, "-m", "pytest", "tests/test_local_playwright_smoke_20260508.py", "-q"),
            180,
            classify_pytest_requires_pass,
        ),
        GateCheck(
            "ai_proxy_contract",
            (py, "-m", "pytest", "tests/test_openai_server_proxy_client.py", "-q"),
            120,
            classify_pytest_requires_pass,
        ),
        GateCheck(
            "server_browser_block_contract",
            (py, "-m", "pytest", "tests/test_no_server_playwright_execution_20260508.py", "-q"),
            60,
            classify_pytest_requires_pass,
        ),
    )


def run_check(check: GateCheck, *, retries: int, retry_delay: float) -> CheckOutcome:
    if command_is_forbidden(check.command):
        return CheckOutcome(check.name, "FAIL", "forbidden command blocked", 0)

    attempts = max(1, retries + 1)
    last_status = "FAIL"
    last_detail = "not run"
    last_output = ""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    for attempt in range(1, attempts + 1):
        print(f"[RUN] {check.name} attempt={attempt}/{attempts} - {command_text(check.command)}")
        try:
            result = subprocess.run(
                list(check.command),
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=check.timeout,
                check=False,
                env=env,
            )
            output = redact(result.stdout or "")
            returncode = result.returncode
        except subprocess.TimeoutExpired as exc:
            output = redact((exc.stdout or "") + "\n" + (exc.stderr or ""))
            output = (output + f"\nTimeoutExpired after {check.timeout}s").strip()
            returncode = 124
        last_output = output
        status, detail = check.classifier(output, returncode)
        last_status, last_detail = status, detail
        print(f"[{status}] {check.name} - {detail}")
        if status in {"PASS", "WARN"}:
            return CheckOutcome(check.name, status, detail, attempt)
        if attempt < attempts:
            reason = "transient marker observed" if has_transient_marker(output) else "failure observed"
            print(f"[WARN] {check.name} - {reason}; retrying after {retry_delay:g}s")
            time.sleep(retry_delay)
            continue
        break
    if last_output:
        tail = last_output[-800:].replace("\n", " | ")
        print(f"[DETAIL] {check.name} - {tail}")
    return CheckOutcome(check.name, last_status, last_detail, attempts)


def print_plan(checks: tuple[GateCheck, ...]) -> None:
    print("Pre-deploy runtime gate plan")
    for check in checks:
        print(f"- {check.name}: {command_text(check.command)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pre-deploy runtime readiness checks")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=8.0)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(argv)

    checks = make_checks(args.server.rstrip("/"))
    if args.plan:
        print_plan(checks)
        return 0

    outcomes: list[CheckOutcome] = []
    for check in checks:
        outcomes.append(run_check(check, retries=args.retries, retry_delay=args.retry_delay))

    failed = [outcome for outcome in outcomes if outcome.status == "FAIL"]
    warned = [outcome for outcome in outcomes if outcome.status == "WARN"]
    print("\nPre-deploy runtime gate summary")
    for outcome in outcomes:
        print(f"- {outcome.status} {outcome.name} attempts={outcome.attempts} detail={outcome.detail}")
    if failed:
        print(f"RESULT=FAIL_PRE_DEPLOY_RUNTIME_GATE failed={len(failed)} warned={len(warned)}")
        return 1
    if warned:
        print(f"RESULT=WARN_PRE_DEPLOY_RUNTIME_GATE failed=0 warned={len(warned)}")
        return 0
    print("RESULT=PASS_PRE_DEPLOY_RUNTIME_GATE failed=0 warned=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
