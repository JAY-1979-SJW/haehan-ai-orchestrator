"""Audit-script-delegating check functions for module_quality_gate."""
from __future__ import annotations

import sys

try:
    from scripts.module_quality_gate_common import PY, _run_check_command
except ModuleNotFoundError:
    from module_quality_gate_common import PY, _run_check_command  # type: ignore[no-redef]

sys.dont_write_bytecode = True


def check_site_registry_baseline() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/validate_site_registry_baseline.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "official site registry covers site modules and policy fields"


def check_site_sso_subdomain_runtime_baseline() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_site_sso_subdomain_runtime_baseline.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "shared SSO subdomain runtime baseline is locked for Google and Naver"


def check_site_work_function_baseline() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_site_work_function_baseline.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked site work function baseline preserves routed work, counts, and approval boundaries"


def check_google_automation_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_automation_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked Google automation baseline preserves tabs, counts, and host rules"


def check_google_workspace_module_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_workspace_module_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked Google Workspace baseline preserves workspace counts and approval boundaries"


def check_google_gmail_function_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_gmail_function_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "Gmail function contract blocks final send/delete and preserves no-final-submit"


def check_google_workspace_router_compatibility() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_workspace_router_compatibility.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "Google Workspace router compatibility and catalog-only safeguards are locked"


def check_google_cloud_module_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_cloud_module_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked Google Cloud baseline preserves cloud counts, host, and security boundaries"


def check_google_cloud_router_compatibility() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_cloud_router_compatibility.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "Google Cloud router compatibility and catalog-only safeguards are locked"


def check_google_cloud_action_policy_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_cloud_action_policy_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked Google Cloud action policy classifies every Cloud action"


def check_google_cloud_readonly_local_browser_dryrun() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_cloud_readonly_local_browser_dryrun.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "Google Cloud read-only contracts convert to local browser dry-run tasks"


def check_google_domain_module_boundaries() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_google_domain_module_boundaries.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "Google domain/module/page/action/input/control/evidence boundaries are locked"


def check_common_tool_runtime_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_common_tool_runtime.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "common tool runtime contract blocks unsafe execution paths"


def check_common_tool_runtime_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_common_tool_runtime_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked common_tool_runtime baseline defines task, risk, approval, and forbidden-field boundaries"


def check_common_engine_commercialization_baseline() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_common_engine_commercialization_baseline.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked common engine commercialization baseline defines engine-first app readiness"


def check_local_agent_connection_recovery_baseline() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_local_agent_connection_recovery_baseline.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked local-agent connection recovery baseline defines repair and reconnect readiness"


def check_desktop_auth_runtime_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_desktop_auth_runtime_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked desktop_auth_runtime baseline defines auth, redaction, and isolation boundaries"


def check_portable_install_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_portable_install_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked portable_install baseline defines no-admin install and diagnostics boundaries"


def check_release_preflight_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_release_preflight_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked release_preflight baseline defines static no-build release checks"


def check_app_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_app_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked app baseline is present and referenced by governance rules"


def check_standard_workflow_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_standard_workflow_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked standard workflow and report template are enforced"


def check_module_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_module_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked module baseline defines module responsibilities and boundaries"


def check_backend_runtime_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_backend_runtime_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "backend runtime route inventory and security patterns are locked"


def check_backend_core_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_backend_core_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked backend_core baseline defines auth, approval, task, and dispatch boundaries"


def check_local_agent_e2e_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_local_agent_e2e_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked local_agent_e2e baseline defines auth, dispatch, state, and redaction boundaries"


def check_approval_flow_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_approval_flow_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked approval_flow baseline defines API-default approval and fail-closed behavior"


def check_playwright_ai_baseline_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/audit_playwright_ai_baseline_contract.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "locked playwright_ai baseline defines local-only execution and redaction boundaries"
