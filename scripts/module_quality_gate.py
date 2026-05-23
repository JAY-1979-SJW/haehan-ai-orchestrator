"""Module-scoped quality gate runner.

This runner groups the repository's verification commands by functional module
so release checks can be run independently without accidentally crossing into
installer builds, Docker operations, deploys, or staged out-of-scope files.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]

OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}

FORBIDDEN_TOKENS = {
    "docker",
    "docker-compose",
    "electron-builder",
    "git add",
    "git commit",
    "git push",
    "npm run build",
    "next build",
    "pyinstaller",
}


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...] = ()
    live: bool = False
    check: str | None = None


@dataclass(frozen=True)
class GateModule:
    name: str
    description: str
    steps: tuple[GateStep, ...]


PY = sys.executable

MODULES: tuple[GateModule, ...] = (
    GateModule(
        name="repo_guard",
        description="git/out-of-scope/build-output guardrails",
        steps=(
            GateStep("out_of_scope_not_staged", check="out_of_scope_not_staged"),
            GateStep("forbidden_command_matrix", check="forbidden_command_matrix"),
            GateStep("desktop_security_boundary", check="desktop_security_boundary"),
        ),
    ),
    GateModule(
        name="portable_install",
        description="portable ZIP install scripts and contract",
        steps=(
            GateStep("portable_py_compile", (PY, "scripts/py_compile_no_cache.py", "verify_portable_zip_install.py")),
            GateStep("portable_static_verify", (PY, "verify_portable_zip_install.py", "--static-only")),
            GateStep(
                "portable_contract_pytest",
                (PY, "-m", "pytest", "tests/test_portable_zip_install_contract.py", "-q"),
            ),
        ),
    ),
    GateModule(
        name="desktop_auth_runtime",
        description="desktop diagnostics, auth token presence, and runtime dry-run",
        steps=(
            GateStep(
                "desktop_auth_py_compile",
                (
                    PY,
                    "scripts/py_compile_no_cache.py",
                    "local_agent/desktop_launcher.py",
                    "verify_agent_ws_auth.py",
                    "verify_local_runtime_dry_run.py",
                ),
            ),
            GateStep(
                "desktop_runtime_static",
                (PY, "verify_local_runtime_dry_run.py"),
            ),
            GateStep(
                "agent_ws_auth_live",
                (PY, "verify_agent_ws_auth.py", "--server", "https://haehan-ai.kr/orchestrator", "--timeout", "15"),
                live=True,
            ),
            GateStep(
                "desktop_runtime_live",
                (PY, "verify_local_runtime_dry_run.py", "--live-server"),
                live=True,
            ),
        ),
    ),
    GateModule(
        name="live_agent",
        description="server connectivity, WebSocket auth, heartbeat, and safe task dispatch",
        steps=(
            GateStep(
                "live_agent_py_compile",
                (PY, "scripts/py_compile_no_cache.py", "verify_live_agent_smoke.py", "verify_live_task_dispatch.py"),
            ),
            GateStep(
                "live_agent_smoke",
                (PY, "verify_live_agent_smoke.py", "--server", "https://haehan-ai.kr/orchestrator", "--timeout", "15"),
                live=True,
            ),
            GateStep(
                "live_task_dispatch",
                (PY, "verify_live_task_dispatch.py", "--server", "https://haehan-ai.kr/orchestrator", "--timeout", "70"),
                live=True,
            ),
        ),
    ),
    GateModule(
        name="playwright_ai",
        description="local Playwright bootstrap and AI proxy no-secret contract",
        steps=(
            GateStep(
                "playwright_bootstrap",
                (PY, "-m", "pytest", "tests/test_local_playwright_bootstrap_20260508.py", "-q"),
                live=True,
            ),
            GateStep(
                "openai_proxy_contract",
                (PY, "-m", "pytest", "tests/test_openai_server_proxy_client.py", "-q"),
            ),
            GateStep(
                "playwright_smoke_live",
                (PY, "-m", "pytest", "tests/test_local_playwright_smoke_20260508.py", "-q"),
                live=True,
            ),
        ),
    ),
)


def module_names() -> list[str]:
    return [module.name for module in MODULES]


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip('"')


def redact(text: str) -> str:
    rules = (
        (re.compile(r"(?i)(Authorization\s*[:=]\s*Bearer\s+)[^\s'\";,]+"), r"\1<redacted>"),
        (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
        (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "sk-<redacted>"),
        (
            re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|device[_-]?token|secret|password)\s*[:=]\s*)[^\s'\";,]+"),
            r"\1<redacted>",
        ),
    )
    redacted = text
    for pattern, replacement in rules:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def command_text(command: Iterable[str]) -> str:
    return " ".join(str(part) for part in command)


def command_is_forbidden(command: Iterable[str]) -> bool:
    lowered = command_text(command).lower()
    return any(token in lowered for token in FORBIDDEN_TOKENS)


def all_steps() -> list[GateStep]:
    return [step for module in MODULES for step in module.steps]


def find_staged_out_of_scope(staged_paths: Iterable[str]) -> list[str]:
    normalized = {normalize_path(path) for path in staged_paths}
    return sorted(path for path in OUT_OF_SCOPE if path in normalized)


def git_staged_paths() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(redact(result.stderr.strip()) or "git diff --cached failed")
    return [normalize_path(line) for line in result.stdout.splitlines() if line.strip()]


def check_out_of_scope_not_staged() -> tuple[bool, str]:
    staged = find_staged_out_of_scope(git_staged_paths())
    if staged:
        return False, "OUT_OF_SCOPE staged: " + ", ".join(staged)
    return True, "OUT_OF_SCOPE files are not staged"


def check_forbidden_command_matrix() -> tuple[bool, str]:
    offenders = [step.name for step in all_steps() if step.command and command_is_forbidden(step.command)]
    if offenders:
        return False, "forbidden commands in module gate matrix: " + ", ".join(offenders)
    return True, "module gate matrix contains no build/deploy/push commands"


def _source_contains(path: str, needles: Iterable[str]) -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    return [needle for needle in needles if needle in text]


def check_desktop_security_boundary() -> tuple[bool, str]:
    """Block auth and cross-app shortcuts from returning to desktop runtime."""
    violations: list[str] = []

    local_agent_forbidden = (
        "class _McpStdioClient",
        "_run_with_anthropic(prompt, mcp",
        "mcp_server/server.py",
        "14. CAD",
        'req.get("_approved")',
        'req.get("approved_api")',
    )
    for hit in _source_contains("desktop/local_agent_service.py", local_agent_forbidden):
        violations.append(f"desktop/local_agent_service.py contains {hit!r}")

    hardcoded_auth_forbidden = (
        "Bearer admin-token",
        "Authorization: Bearer admin-token",
        '"Authorization": "Bearer admin-token"',
        "'Authorization': 'Bearer admin-token'",
    )
    for path in (
        "desktop/task_receiver.py",
        "desktop/local_agent_service.py",
        "desktop/local_server.py",
    ):
        for hit in _source_contains(path, hardcoded_auth_forbidden):
            violations.append(f"{path} contains {hit!r}")

    allowed_cad_boundary_imports = {
        "desktop/cad_api_approval.py",
        "desktop/cad_bridge_allowlist.py",
    }
    for path in (ROOT / "desktop").glob("*.py"):
        rel = normalize_path(str(path.relative_to(ROOT)))
        if rel in allowed_cad_boundary_imports:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "from local_agent.cad" in text or "import local_agent.cad" in text:
            violations.append(f"{rel} imports local_agent.cad outside boundary")
        if rel in {"desktop/tray_runtime.py", "desktop/main_launcher.py"}:
            if "from local_agent" in text or "import local_agent" in text:
                violations.append(f"{rel} imports local_agent outside boundary")

    if violations:
        return False, "; ".join(violations)
    return True, "desktop auth/cross-app shortcuts are blocked and runtime boundary imports are isolated"


CHECKS: dict[str, Callable[[], tuple[bool, str]]] = {
    "out_of_scope_not_staged": check_out_of_scope_not_staged,
    "forbidden_command_matrix": check_forbidden_command_matrix,
    "desktop_security_boundary": check_desktop_security_boundary,
}


def selected_modules(names: list[str]) -> list[GateModule]:
    if not names or names == ["all"]:
        return list(MODULES)
    known = {module.name: module for module in MODULES}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError("unknown module(s): " + ", ".join(unknown))
    return [known[name] for name in names]


def iter_selected_steps(modules: Iterable[GateModule], *, include_live: bool) -> Iterable[tuple[GateModule, GateStep]]:
    for module in modules:
        for step in module.steps:
            if step.live and not include_live:
                continue
            yield module, step


def run_step(step: GateStep, *, dry_run: bool) -> bool:
    if step.check:
        ok, message = CHECKS[step.check]()
        print(f"[{'PASS' if ok else 'FAIL'}] {step.name} - {message}")
        return ok

    if not step.command:
        print(f"[FAIL] {step.name} - missing command")
        return False
    if command_is_forbidden(step.command):
        print(f"[FAIL] {step.name} - forbidden command blocked")
        return False

    display = command_text(step.command)
    if dry_run:
        print(f"[DRY-RUN] {step.name} - {display}")
        return True

    print(f"[RUN] {step.name} - {display}")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    pycache = Path(
        os.environ.get("HAEHAN_MODULE_GATE_PYCACHE", str(Path(os.environ["TEMP"]) / "haehan_module_gate_pycache"))
    )
    pycache.mkdir(parents=True, exist_ok=True)
    env.setdefault("PYTHONPYCACHEPREFIX", str(pycache))
    result = subprocess.run(
        list(step.command),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=env,
    )
    output = redact(result.stdout or "")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] {step.name} exit_code={result.returncode}")
    return result.returncode == 0


def print_module_list() -> None:
    print("Module gates")
    for module in MODULES:
        live_count = sum(1 for step in module.steps if step.live)
        static_count = len(module.steps) - live_count
        print(f"- {module.name}: {module.description} ({static_count} static, {live_count} live)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run module-scoped quality gates")
    parser.add_argument("--module", action="append", choices=["all", *module_names()], help="module to run; repeatable")
    parser.add_argument("--include-live", action="store_true", help="include live server/browser checks")
    parser.add_argument("--dry-run", action="store_true", help="print commands without executing them")
    parser.add_argument("--list", action="store_true", help="list available module gates")
    args = parser.parse_args(argv)

    if args.list:
        print_module_list()
        return 0

    modules = selected_modules(args.module or ["all"])
    steps = list(iter_selected_steps(modules, include_live=args.include_live))
    if not steps:
        print("No gate steps selected")
        return 2

    print("Module quality gate")
    print(f"modules={','.join(module.name for module in modules)} include_live={args.include_live} dry_run={args.dry_run}")
    passed = 0
    failed = 0
    for module, step in steps:
        print(f"\n[{module.name}] {step.name}")
        if run_step(step, dry_run=args.dry_run):
            passed += 1
        else:
            failed += 1

    print(f"\nRESULT={'PASS_MODULE_QUALITY_GATE' if failed == 0 else 'FAIL_MODULE_QUALITY_GATE'} passed={passed} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
