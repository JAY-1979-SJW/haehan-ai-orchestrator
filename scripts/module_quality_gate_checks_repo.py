"""Repository-guard check functions for module_quality_gate."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys

try:
    from scripts.module_quality_gate_common import (
        PY,
        ROOT,
        _run_check_command,
        all_steps,
        command_is_forbidden,
        find_staged_out_of_scope,
        git_staged_paths,
        normalize_path,
    )
except ModuleNotFoundError:
    from module_quality_gate_common import (  # type: ignore[no-redef]
        PY,
        ROOT,
        _run_check_command,
        all_steps,
        command_is_forbidden,
        find_staged_out_of_scope,
        git_staged_paths,
        normalize_path,
    )

sys.dont_write_bytecode = True


def imports_local_agent(text: str) -> bool:
    return bool(
        re.search(
            r"(?m)^\s*(?:from\s+local_agent(?:\.|\s+import\b)|import\s+local_agent(?:\.|\s|$))",
            text,
        )
    )


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


def check_local_agent_browser_runtime_rules() -> tuple[bool, str]:
    doc = ROOT / "docs" / "architecture" / "local_agent_browser_runtime_operating_rules_20260523.md"
    dry_run = ROOT / "scripts" / "ops" / "dry_run_local_agent_cdp_attach.py"
    tests = ROOT / "tests" / "test_local_agent_browser_runtime_operating_rules.py"
    monitor = ROOT / "scripts" / "archive" / "misc" / "chrome_ui_monitor.py"
    cdp_client = ROOT / "scripts" / "cdp_client.py"

    required_files = (doc, dry_run, tests, monitor, cdp_client)
    missing = [normalize_path(str(path.relative_to(ROOT))) for path in required_files if not path.exists()]
    if missing:
        return False, "missing browser runtime gate file(s): " + ", ".join(missing)

    doc_text = doc.read_text(encoding="utf-8", errors="replace")
    required_doc_phrases = (
        "Status: LOCKED",
        "CDP attach is local-only",
        "CDP discovery is read-only",
        "CDP output is redacted",
        "Automated browser execution uses a dedicated profile",
        "Runtime state must not be written under `scripts/archive`",
    )
    missing_phrases = [phrase for phrase in required_doc_phrases if phrase not in doc_text]
    if missing_phrases:
        return False, "browser runtime policy doc missing phrase(s): " + ", ".join(missing_phrases)

    runtime_state_literal = '"data" / "runtime" / "chrome_ui_monitor_state.json"'
    archive_state_literal = '"data" / "chrome_ui_monitor_state.json"'
    for path in (monitor, cdp_client):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = normalize_path(str(path.relative_to(ROOT)))
        if runtime_state_literal not in text:
            return False, f"{rel} does not use data/runtime chrome UI monitor state"
        if archive_state_literal in text:
            return False, f"{rel} still references archive/data chrome UI monitor state"

    dry_run_text = dry_run.read_text(encoding="utf-8", errors="replace")
    if "chrome_ui_monitor_runtime_path" not in dry_run_text:
        return False, "CDP attach dry-run does not enforce chrome UI monitor runtime path"

    ok, message = _run_check_command(
        [
            PY,
            "-m",
            "pytest",
            "tests/test_local_agent_browser_runtime_operating_rules.py",
            "tests/test_local_agent_cdp_attach.py",
            "tests/test_dry_run_local_agent_cdp_attach.py",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        timeout=180,
    )
    if not ok:
        return False, "browser runtime operating rule pytest failed: " + message
    return True, "browser runtime operating rules are locked by policy, dry-run, and pytest"


def check_required_local_gate_wiring() -> tuple[bool, str]:
    workflows_dir = ROOT / ".github" / "workflows"
    workflow_files = []
    if workflows_dir.exists():
        workflow_files = [
            normalize_path(str(path.relative_to(ROOT)))
            for path in workflows_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
        ]
    if workflow_files:
        return False, "GitHub Actions workflow files are forbidden: " + ", ".join(sorted(workflow_files))

    required_gate = ROOT / "scripts" / "required_quality_gate.py"
    pre_commit = ROOT / ".githooks" / "pre-commit"
    pre_push = ROOT / ".githooks" / "pre-push"
    required_files = (required_gate, pre_commit, pre_push)
    missing = [normalize_path(str(path.relative_to(ROOT))) for path in required_files if not path.exists()]
    if missing:
        return False, "missing required local gate file(s): " + ", ".join(missing)

    hook_call = "python scripts/required_quality_gate.py"
    for hook in (pre_commit, pre_push):
        text = hook.read_text(encoding="utf-8", errors="replace")
        rel = normalize_path(str(hook.relative_to(ROOT)))
        if hook_call not in text:
            return False, f"{rel} does not delegate to scripts/required_quality_gate.py"

    spec = importlib.util.spec_from_file_location("required_quality_gate", required_gate)
    if spec is None or spec.loader is None:
        return False, "required_quality_gate import spec failed"
    required_gate_mod = importlib.util.module_from_spec(spec)
    try:
        sys.modules[spec.name] = required_gate_mod
        spec.loader.exec_module(required_gate_mod)
    except Exception as exc:
        return False, f"required_quality_gate import failed: {type(exc).__name__}"

    offenders = [
        required_gate_mod.command_text(command)
        for command in required_gate_mod.COMMANDS
        if required_gate_mod.command_is_forbidden(command)
    ]
    if offenders:
        return False, "required gate contains forbidden command(s): " + "; ".join(offenders)

    required_rendered = "\n".join(required_gate_mod.command_text(command) for command in required_gate_mod.COMMANDS)
    required_needles = (
        "scripts/ops/dry_run_local_agent_cdp_attach.py",
        "tests/test_local_agent_browser_runtime_operating_rules.py",
        "tests/test_local_agent_cdp_attach.py",
        "tests/test_dry_run_local_agent_cdp_attach.py",
        "tests/test_common_tool_runtime.py",
        "tests/test_common_tool_runtime_baseline_contract.py",
        "tests/test_common_engine_commercialization_baseline.py",
        "tests/test_local_agent_connection_recovery_baseline.py",
        "tests/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_local_agent_e2e_flow_contract.py",
        "tests/test_app_baseline_contract.py",
        "tests/test_standard_workflow_contract.py",
        "tests/test_module_baseline_contract.py",
        "tests/test_backend_core_baseline_contract.py",
        "tests/test_local_agent_e2e_baseline_contract.py",
        "tests/test_approval_flow_baseline_contract.py",
        "tests/test_playwright_ai_baseline_contract.py",
        "tests/test_required_quality_gate.py",
        "tests/test_root_legacy_scripts_audit.py",
        "scripts/ops/audit_common_tool_runtime.py",
        "scripts/ops/audit_common_tool_runtime_baseline_contract.py",
        "scripts/ops/audit_common_engine_commercialization_baseline.py",
        "scripts/ops/audit_local_agent_connection_recovery_baseline.py",
        "scripts/ops/audit_desktop_auth_runtime_baseline_contract.py",
        "scripts/ops/audit_local_agent_e2e_flow_contract.py",
        "scripts/ops/audit_app_baseline_contract.py",
        "scripts/ops/audit_standard_workflow_contract.py",
        "scripts/ops/audit_module_baseline_contract.py",
        "scripts/ops/audit_backend_core_baseline_contract.py",
        "scripts/ops/audit_local_agent_e2e_baseline_contract.py",
        "scripts/ops/audit_approval_flow_baseline_contract.py",
        "scripts/ops/audit_playwright_ai_baseline_contract.py",
        "scripts/ops/audit_root_legacy_scripts.py",
        "scripts/module_quality_gate.py --module repo_guard",
    )
    missing_needles = [needle for needle in required_needles if needle not in required_rendered]
    if missing_needles:
        return False, "required gate missing command target(s): " + ", ".join(missing_needles)

    config = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    hooks_path = normalize_path(config.stdout.strip()) if config.returncode == 0 else ""
    if hooks_path != ".githooks":
        return False, "core.hooksPath must be .githooks; run python scripts/install_git_hooks.py"

    return True, "required local gate is wired through pre-commit/pre-push and Actions are disabled"


def check_module_boundary_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_module_boundaries.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "module boundary map and audit pass"


def check_root_legacy_script_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_root_legacy_scripts.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "root legacy script inventory is classified and locked"
