"""CHECKS registry, run_step, print_module_list, and main CLI for module_quality_gate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

try:
    from tools.quality.module_quality_gate_checks_audit import (
        check_app_baseline_contract,
        check_approval_flow_baseline_contract,
        check_backend_core_baseline_contract,
        check_backend_runtime_contract,
        check_common_engine_commercialization_baseline,
        check_common_tool_runtime_baseline_contract,
        check_common_tool_runtime_contract,
        check_desktop_auth_runtime_baseline_contract,
        check_google_automation_baseline_contract,
        check_google_cloud_action_policy_baseline_contract,
        check_google_cloud_module_baseline_contract,
        check_google_cloud_readonly_local_browser_dryrun,
        check_google_cloud_router_compatibility,
        check_google_domain_module_boundaries,
        check_google_gmail_function_contract,
        check_google_workspace_module_baseline_contract,
        check_google_workspace_router_compatibility,
        check_local_agent_connection_recovery_baseline,
        check_local_agent_e2e_baseline_contract,
        check_module_baseline_contract,
        check_playwright_ai_baseline_contract,
        check_site_registry_baseline,
        check_site_sso_subdomain_runtime_baseline,
        check_site_work_function_baseline,
        check_standard_workflow_contract,
    )
    from tools.quality.module_quality_gate_checks_repo import (
        check_forbidden_command_matrix,
        check_local_agent_browser_runtime_rules,
        check_module_boundary_contract,
        check_out_of_scope_not_staged,
        check_required_local_gate_wiring,
        check_root_legacy_script_contract,
    )
    from tools.quality.module_quality_gate_checks_web import (
        check_active_source_secret_scan,
        check_admin_web_audit,
        check_admin_web_lint,
        check_admin_web_typecheck,
    )
    from tools.quality.module_quality_gate_common import (
        ROOT,
        GateStep,
        command_is_forbidden,
        command_text,
        redact,
        workspace_temp_root,
    )
    from tools.quality.module_quality_gate_modules import (
        MODULES,
        iter_selected_steps,
        module_names,
        selected_modules,
    )
except ModuleNotFoundError:
    from module_quality_gate_checks_audit import (  # type: ignore[no-redef, import-not-found]
        check_app_baseline_contract,
        check_approval_flow_baseline_contract,
        check_backend_core_baseline_contract,
        check_backend_runtime_contract,
        check_common_engine_commercialization_baseline,
        check_common_tool_runtime_baseline_contract,
        check_common_tool_runtime_contract,
        check_desktop_auth_runtime_baseline_contract,
        check_google_automation_baseline_contract,
        check_google_cloud_action_policy_baseline_contract,
        check_google_cloud_module_baseline_contract,
        check_google_cloud_readonly_local_browser_dryrun,
        check_google_cloud_router_compatibility,
        check_google_domain_module_boundaries,
        check_google_gmail_function_contract,
        check_google_workspace_module_baseline_contract,
        check_google_workspace_router_compatibility,
        check_local_agent_connection_recovery_baseline,
        check_local_agent_e2e_baseline_contract,
        check_module_baseline_contract,
        check_playwright_ai_baseline_contract,
        check_site_registry_baseline,
        check_site_sso_subdomain_runtime_baseline,
        check_site_work_function_baseline,
        check_standard_workflow_contract,
    )
    from module_quality_gate_checks_repo import (  # type: ignore[no-redef, import-not-found]
        check_forbidden_command_matrix,
        check_local_agent_browser_runtime_rules,
        check_module_boundary_contract,
        check_out_of_scope_not_staged,
        check_required_local_gate_wiring,
        check_root_legacy_script_contract,
    )
    from module_quality_gate_checks_web import (  # type: ignore[no-redef, import-not-found]
        check_active_source_secret_scan,
        check_admin_web_audit,
        check_admin_web_lint,
        check_admin_web_typecheck,
    )
    from module_quality_gate_common import (  # type: ignore[no-redef, import-not-found]
        ROOT,
        GateStep,
        command_is_forbidden,
        command_text,
        redact,
        workspace_temp_root,
    )
    from module_quality_gate_modules import (  # type: ignore[no-redef, import-not-found]
        MODULES,
        iter_selected_steps,
        module_names,
        selected_modules,
    )

sys.dont_write_bytecode = True


CHECKS: dict[str, Callable[[], tuple[bool, str]]] = {
    "out_of_scope_not_staged": check_out_of_scope_not_staged,
    "forbidden_command_matrix": check_forbidden_command_matrix,
    "desktop_auth_runtime_baseline_contract": check_desktop_auth_runtime_baseline_contract,
    "local_agent_browser_runtime_rules": check_local_agent_browser_runtime_rules,
    "common_tool_runtime_baseline_contract": check_common_tool_runtime_baseline_contract,
    "common_engine_commercialization_baseline": check_common_engine_commercialization_baseline,
    "local_agent_connection_recovery_baseline": check_local_agent_connection_recovery_baseline,
    "common_tool_runtime_contract": check_common_tool_runtime_contract,
    "app_baseline_contract": check_app_baseline_contract,
    "standard_workflow_contract": check_standard_workflow_contract,
    "module_baseline_contract": check_module_baseline_contract,
    "backend_core_baseline_contract": check_backend_core_baseline_contract,
    "local_agent_e2e_baseline_contract": check_local_agent_e2e_baseline_contract,
    "approval_flow_baseline_contract": check_approval_flow_baseline_contract,
    "playwright_ai_baseline_contract": check_playwright_ai_baseline_contract,
    "backend_runtime_contract": check_backend_runtime_contract,
    "required_local_gate_wiring": check_required_local_gate_wiring,
    "module_boundary_contract": check_module_boundary_contract,
    "root_legacy_script_contract": check_root_legacy_script_contract,
    "site_registry_baseline": check_site_registry_baseline,
    "site_sso_subdomain_runtime_baseline": check_site_sso_subdomain_runtime_baseline,
    "site_work_function_baseline": check_site_work_function_baseline,
    "google_automation_baseline_contract": check_google_automation_baseline_contract,
    "google_workspace_module_baseline_contract": check_google_workspace_module_baseline_contract,
    "google_gmail_function_contract": check_google_gmail_function_contract,
    "google_workspace_router_compatibility": check_google_workspace_router_compatibility,
    "google_cloud_module_baseline_contract": check_google_cloud_module_baseline_contract,
    "google_cloud_router_compatibility": check_google_cloud_router_compatibility,
    "google_cloud_action_policy_baseline_contract": check_google_cloud_action_policy_baseline_contract,
    "google_cloud_readonly_local_browser_dryrun": check_google_cloud_readonly_local_browser_dryrun,
    "google_domain_module_boundaries": check_google_domain_module_boundaries,
    "admin_web_typecheck": check_admin_web_typecheck,
    "admin_web_lint": check_admin_web_lint,
    "admin_web_audit": check_admin_web_audit,
    "active_source_secret_scan": check_active_source_secret_scan,
}


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
    temp_root = workspace_temp_root(env, step.name)
    env["TMP"] = str(temp_root)
    env["TEMP"] = str(temp_root)
    env["TMPDIR"] = str(temp_root)
    pycache = Path(env.get("HAEHAN_MODULE_GATE_PYCACHE", str(temp_root / "pycache")))
    pycache.mkdir(parents=True, exist_ok=True)
    env.setdefault("PYTHONPYCACHEPREFIX", str(pycache))
    runtime_command = list(step.command)
    result = subprocess.run(
        runtime_command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=env,
        encoding="utf-8",
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
    print(
        f"modules={','.join(module.name for module in modules)} include_live={args.include_live} dry_run={args.dry_run}"
    )
    passed = 0
    failed = 0
    for module, step in steps:
        print(f"\n[{module.name}] {step.name}")
        if run_step(step, dry_run=args.dry_run):
            passed += 1
        else:
            failed += 1

    print(
        f"\nRESULT={'PASS_MODULE_QUALITY_GATE' if failed == 0 else 'FAIL_MODULE_QUALITY_GATE'} passed={passed} failed={failed}"
    )
    return 0 if failed == 0 else 1
