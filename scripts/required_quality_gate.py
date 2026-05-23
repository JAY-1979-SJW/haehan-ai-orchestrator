"""Repository-owned required quality gate.

This replaces GitHub Actions for the locked local-agent browser runtime checks.
It is designed for local pre-commit/pre-push execution and does not build,
deploy, push, run Docker, or start browsers.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMMANDS: tuple[tuple[str, ...], ...] = (
    (
        sys.executable,
        "-m",
        "py_compile",
        "local_agent/cdp_attach.py",
        "scripts/archive/misc/chrome_ui_monitor.py",
        "scripts/cdp_client.py",
        "scripts/ops/dry_run_local_agent_cdp_attach.py",
        "scripts/ops/audit_common_tool_runtime.py",
        "scripts/ops/audit_common_tool_runtime_baseline_contract.py",
        "scripts/ops/audit_desktop_auth_runtime_baseline_contract.py",
        "scripts/ops/audit_portable_install_baseline_contract.py",
        "scripts/ops/audit_local_agent_e2e_flow_contract.py",
        "scripts/ops/audit_app_baseline_contract.py",
        "scripts/ops/audit_standard_workflow_contract.py",
        "scripts/ops/audit_module_baseline_contract.py",
        "scripts/ops/audit_backend_core_baseline_contract.py",
        "scripts/ops/audit_local_agent_e2e_baseline_contract.py",
        "scripts/ops/audit_approval_flow_baseline_contract.py",
        "scripts/ops/audit_playwright_ai_baseline_contract.py",
        "scripts/ops/audit_module_boundaries.py",
        "scripts/ops/audit_root_legacy_scripts.py",
        "ai_orchestrator/local_agent/common_tool_runtime.py",
        "scripts/module_quality_gate.py",
        "tests/test_common_tool_runtime.py",
        "tests/test_common_tool_runtime_baseline_contract.py",
        "tests/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_portable_install_baseline_contract.py",
        "tests/test_local_agent_e2e_flow_contract.py",
        "tests/test_app_baseline_contract.py",
        "tests/test_standard_workflow_contract.py",
        "tests/test_module_baseline_contract.py",
        "tests/test_backend_core_baseline_contract.py",
        "tests/test_local_agent_e2e_baseline_contract.py",
        "tests/test_approval_flow_baseline_contract.py",
        "tests/test_playwright_ai_baseline_contract.py",
        "tests/test_local_agent_browser_runtime_operating_rules.py",
        "tests/test_local_agent_cdp_attach.py",
        "tests/test_dry_run_local_agent_cdp_attach.py",
        "tests/test_module_quality_gate.py",
        "tests/test_required_quality_gate.py",
        "tests/test_module_boundaries.py",
        "tests/test_root_legacy_scripts_audit.py",
    ),
    (sys.executable, "scripts/ops/dry_run_local_agent_cdp_attach.py"),
    (sys.executable, "scripts/ops/audit_common_tool_runtime.py"),
    (sys.executable, "scripts/ops/audit_common_tool_runtime_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_desktop_auth_runtime_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_portable_install_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_local_agent_e2e_flow_contract.py"),
    (sys.executable, "scripts/ops/audit_app_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_standard_workflow_contract.py"),
    (sys.executable, "scripts/ops/audit_module_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_backend_core_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_local_agent_e2e_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_approval_flow_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_playwright_ai_baseline_contract.py"),
    (sys.executable, "scripts/ops/audit_module_boundaries.py"),
    (sys.executable, "scripts/ops/audit_root_legacy_scripts.py"),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_common_tool_runtime.py",
        "tests/test_common_tool_runtime_baseline_contract.py",
        "tests/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_portable_install_baseline_contract.py",
        "tests/test_local_agent_e2e_flow_contract.py",
        "tests/test_app_baseline_contract.py",
        "tests/test_standard_workflow_contract.py",
        "tests/test_module_baseline_contract.py",
        "tests/test_backend_core_baseline_contract.py",
        "tests/test_local_agent_e2e_baseline_contract.py",
        "tests/test_approval_flow_baseline_contract.py",
        "tests/test_playwright_ai_baseline_contract.py",
        "tests/test_local_agent_browser_runtime_operating_rules.py",
        "tests/test_local_agent_cdp_attach.py",
        "tests/test_dry_run_local_agent_cdp_attach.py",
        "tests/test_required_quality_gate.py",
        "tests/test_module_boundaries.py",
        "tests/test_root_legacy_scripts_audit.py",
        "-p",
        "no:cacheprovider",
        "-q",
    ),
    (sys.executable, "scripts/module_quality_gate.py", "--module", "repo_guard"),
)

FORBIDDEN_COMMAND_TOKENS = {
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
class GateResult:
    name: str
    ok: bool
    detail: str


def redact(text: str) -> str:
    rules = (
        (re.compile(r"(?i)(Authorization\s*[:=]\s*Bearer\s+)[^\s'\";,]+"), r"\1<redacted>"),
        (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
        (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "sk-<redacted>"),
        (
            re.compile(
                r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|device[_-]?token|secret|password)\s*[:=]\s*)[^\s'\";,]+"
            ),
            r"\1<redacted>",
        ),
    )
    redacted = text
    for pattern, replacement in rules:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def command_text(command: tuple[str, ...]) -> str:
    return " ".join(command)


def command_is_forbidden(command: tuple[str, ...]) -> bool:
    lowered = command_text(command).lower()
    return any(token in lowered for token in FORBIDDEN_COMMAND_TOKENS)


def run_command(command: tuple[str, ...]) -> GateResult:
    name = command_text(command)
    if command_is_forbidden(command):
        return GateResult(name=name, ok=False, detail="forbidden command blocked")

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    pycache = Path(env.get("HAEHAN_REQUIRED_GATE_PYCACHE", str(Path(env.get("TEMP", str(ROOT / "tmp"))) / "haehan_required_gate_pycache")))
    pycache.mkdir(parents=True, exist_ok=True)
    env.setdefault("PYTHONPYCACHEPREFIX", str(pycache))

    result = subprocess.run(
        list(command),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=env,
    )
    output = redact(result.stdout or "").strip()
    if output:
        print(output)
    return GateResult(name=name, ok=result.returncode == 0, detail=f"exit_code={result.returncode}")


def main() -> int:
    print("Required quality gate")
    failed = 0
    for command in COMMANDS:
        print(f"\n[RUN] {command_text(command)}")
        result = run_command(command)
        if result.ok:
            print(f"[PASS] {result.detail}")
        else:
            print(f"[FAIL] {result.detail}")
            failed += 1
            break
    print(f"\nRESULT={'PASS_REQUIRED_QUALITY_GATE' if failed == 0 else 'FAIL_REQUIRED_QUALITY_GATE'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
