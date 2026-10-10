"""MODULES registry and module selection helpers for module_quality_gate."""

from __future__ import annotations

import sys

try:
    from tools.quality.module_quality_gate_common import PY, GateModule, GateStep
except ModuleNotFoundError:
    from module_quality_gate_common import PY, GateModule, GateStep  # type: ignore[no-redef, import-not-found]

sys.dont_write_bytecode = True

MODULES: tuple[GateModule, ...] = (
    GateModule(
        name="repo_guard",
        description="git/out-of-scope/build-output guardrails",
        steps=(
            GateStep("out_of_scope_not_staged", check="out_of_scope_not_staged"),
            GateStep("forbidden_command_matrix", check="forbidden_command_matrix"),
            GateStep("local_agent_browser_runtime_rules", check="local_agent_browser_runtime_rules"),
            GateStep("common_tool_runtime_baseline_contract", check="common_tool_runtime_baseline_contract"),
            GateStep("common_engine_commercialization_baseline", check="common_engine_commercialization_baseline"),
            GateStep("local_agent_connection_recovery_baseline", check="local_agent_connection_recovery_baseline"),
            GateStep("common_tool_runtime_contract", check="common_tool_runtime_contract"),
            GateStep("app_baseline_contract", check="app_baseline_contract"),
            GateStep("standard_workflow_contract", check="standard_workflow_contract"),
            GateStep("module_baseline_contract", check="module_baseline_contract"),
            GateStep("required_local_gate_wiring", check="required_local_gate_wiring"),
            GateStep("module_boundary_contract", check="module_boundary_contract"),
            GateStep("root_legacy_script_contract", check="root_legacy_script_contract"),
            GateStep("site_registry_baseline", check="site_registry_baseline"),
            GateStep("site_sso_subdomain_runtime_baseline", check="site_sso_subdomain_runtime_baseline"),
            GateStep("site_work_function_baseline", check="site_work_function_baseline"),
            GateStep("google_automation_baseline_contract", check="google_automation_baseline_contract"),
            GateStep("google_workspace_module_baseline_contract", check="google_workspace_module_baseline_contract"),
            GateStep("google_gmail_function_contract", check="google_gmail_function_contract"),
            GateStep("google_workspace_router_compatibility", check="google_workspace_router_compatibility"),
            GateStep("google_cloud_module_baseline_contract", check="google_cloud_module_baseline_contract"),
            GateStep("google_cloud_router_compatibility", check="google_cloud_router_compatibility"),
            GateStep(
                "google_cloud_action_policy_baseline_contract", check="google_cloud_action_policy_baseline_contract"
            ),
            GateStep("google_cloud_readonly_local_browser_dryrun", check="google_cloud_readonly_local_browser_dryrun"),
            GateStep("google_domain_module_boundaries", check="google_domain_module_boundaries"),
        ),
    ),
    GateModule(
        name="common_engine_commercialization",
        description="engine-first commercial readiness contract and app control-surface boundary",
        steps=(
            GateStep("common_engine_commercialization_baseline", check="common_engine_commercialization_baseline"),
            GateStep(
                "common_engine_commercialization_py_compile",
                (
                    PY,
                    "tools/quality/py_compile_no_cache.py",
                    "scripts/ops/audit_common_engine_commercialization_baseline.py",
                    "tests/app_contracts/test_common_engine_commercialization_baseline.py",
                ),
            ),
            GateStep(
                "common_engine_commercialization_pytest",
                (
                    PY,
                    "-m",
                    "pytest",
                    "tests/app_contracts/test_common_engine_commercialization_baseline.py",
                    "-p",
                    "no:cacheprovider",
                    "-q",
                ),
            ),
        ),
    ),
    GateModule(
        name="local_agent_connection_recovery",
        description="local-agent registration repair, WebSocket auth, heartbeat, and reconnect recovery",
        steps=(
            GateStep("local_agent_connection_recovery_baseline", check="local_agent_connection_recovery_baseline"),
            GateStep(
                "local_agent_connection_recovery_py_compile",
                (
                    PY,
                    "tools/quality/py_compile_no_cache.py",
                    "tools/audits/agent/audit_local_agent_connection_recovery_baseline.py",
                    "tests/test_local_agent_connection_recovery_baseline.py",
                    "tools/verify/verify_agent_ws_auth.py",
                    "tools/verify/verify_live_agent_smoke.py",
                    "tools/verify/verify_live_task_dispatch.py",
                ),
            ),
            GateStep(
                "local_agent_connection_recovery_pytest",
                (
                    PY,
                    "-m",
                    "pytest",
                    "tests/test_local_agent_connection_recovery_baseline.py",
                    "tests/test_local_agent_connection_repair.py",
                    "tests/test_live_agent_smoke_recovery.py",
                    "-p",
                    "no:cacheprovider",
                    "-q",
                ),
            ),
        ),
    ),
    GateModule(
        name="desktop_auth_runtime",
        description="desktop diagnostics, auth token presence, and runtime dry-run",
        steps=(
            GateStep("desktop_auth_runtime_baseline_contract", check="desktop_auth_runtime_baseline_contract"),
            GateStep(
                "desktop_auth_py_compile",
                (
                    PY,
                    "tools/quality/py_compile_no_cache.py",
                    "local_agent/desktop_launcher.py",
                    "tools/verify/verify_agent_ws_auth.py",
                    "tools/verify/verify_local_runtime_dry_run.py",
                ),
            ),
            GateStep(
                "desktop_runtime_static",
                (PY, "tools/verify/verify_local_runtime_dry_run.py"),
            ),
            GateStep(
                "agent_ws_auth_live",
                (
                    PY,
                    "tools/verify/verify_agent_ws_auth.py",
                    "--server",
                    "https://haehan-ai.kr/orchestrator",
                    "--timeout",
                    "15",
                ),
                live=True,
            ),
            GateStep(
                "desktop_runtime_live",
                (PY, "tools/verify/verify_local_runtime_dry_run.py", "--live-server"),
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
                (
                    PY,
                    "tools/quality/py_compile_no_cache.py",
                    "tools/verify/verify_live_agent_smoke.py",
                    "tools/verify/verify_live_task_dispatch.py",
                ),
            ),
            GateStep(
                "live_agent_smoke",
                (
                    PY,
                    "tools/verify/verify_live_agent_smoke.py",
                    "--server",
                    "https://haehan-ai.kr/orchestrator",
                    "--timeout",
                    "15",
                ),
                live=True,
            ),
            GateStep(
                "live_task_dispatch",
                (
                    PY,
                    "tools/verify/verify_live_task_dispatch.py",
                    "--server",
                    "https://haehan-ai.kr/orchestrator",
                    "--timeout",
                    "70",
                ),
                live=True,
            ),
        ),
    ),
    GateModule(
        name="backend_core",
        description="backend module boundaries, route inventory, auth/security gates",
        steps=(
            GateStep("backend_core_baseline_contract", check="backend_core_baseline_contract"),
            GateStep("approval_flow_baseline_contract", check="approval_flow_baseline_contract"),
            GateStep(
                "backend_core_py_compile",
                (
                    PY,
                    "tools/quality/py_compile_no_cache.py",
                    "ai_orchestrator/asgi.py",
                    "ai_orchestrator/routers/registry.py",
                    "tools/gates/auth.py",
                    "ai_orchestrator/auth/auth_router.py",
                    "tools/gates/approval.py",
                    "ai_orchestrator/web_task/web_task_router.py",
                    "ai_orchestrator/services",  # 폴더째 컴파일 — 파일 하나를 이름으로 적으면 새 서비스가 빠지고, 코드맵이 services↔scripts 순환으로 읽는다
                    "ai_orchestrator/agent_hub/router/root.py",
                    "ai_orchestrator/agent_hub/registry/facade.py",
                    "ai_orchestrator/server/action_task_api.py",
                    "ai_orchestrator/server/local_agent_task_api.py",
                    "ai_orchestrator/server/server_egress_policy.py",
                    "ai_orchestrator/server/execution_location_guard.py",
                    "ai_orchestrator/server/external_url_blocker.py",
                    "tools/audits/backend/audit_backend_runtime_contract.py",
                ),
            ),
            GateStep("backend_runtime_contract", check="backend_runtime_contract"),
            GateStep(
                "backend_core_pytest",
                (
                    PY,
                    "-m",
                    "pytest",
                    "tests/app_contracts/test_backend_runtime_contract_gate.py",
                    "tests/app_contracts/test_backend_api_contract_audit_20260516.py",
                    "tests/app_contracts/test_backend_service_layer_task_policy_20260516.py",
                    "tests/app_contracts/test_backend_policy_layer_safety_registry_20260516.py",
                    "tests/app_contracts/test_backend_router_server_cycle_break_20260516.py",
                    "tests/app_contracts/test_backend_direct_dict_boundary_lock_20260516.py",
                    "tests/app_contracts/test_backend_operation_final_closeout_20260518.py",
                    "tests/app_contracts/test_server_local_agent_task_api_20260508.py",
                    "tests/app_contracts/test_server_action_task_api_wiring_20260509.py",
                    "tests/app_contracts/test_server_task_api_approval_gate_20260509.py",
                    "tests/app_contracts/test_server_egress_policy_20260508.py",
                    "tests/app_contracts/test_server_side_external_web_execution_guard_20260508.py",
                    "tests/test_no_server_playwright_execution_20260508.py",
                    "tests/test_authed_local_agent_dispatch_dry_run.py",
                    "-p",
                    "no:cacheprovider",
                    "-q",
                ),
            ),
        ),
    ),
    GateModule(
        name="local_agent_e2e",
        description="approved server task to authenticated local-agent WebSocket result contract",
        steps=(
            GateStep("local_agent_e2e_baseline_contract", check="local_agent_e2e_baseline_contract"),
            GateStep(
                "local_agent_e2e_py_compile",
                (
                    PY,
                    "tools/quality/py_compile_no_cache.py",
                    "tools/audits/agent/audit_local_agent_e2e_flow_contract.py",
                    "tests/test_local_agent_e2e_flow_contract.py",
                ),
            ),
            GateStep(
                "local_agent_e2e_contract",
                (PY, "tools/audits/agent/audit_local_agent_e2e_flow_contract.py"),
            ),
            GateStep(
                "local_agent_e2e_pytest",
                (
                    PY,
                    "-m",
                    "pytest",
                    "tests/test_local_agent_e2e_flow_contract.py",
                    "ai_orchestrator/tests/test_local_agent_ws.py",
                    "-p",
                    "no:cacheprovider",
                    "-q",
                ),
            ),
        ),
    ),
    GateModule(
        name="playwright_ai",
        description="local Playwright bootstrap and AI proxy no-secret contract",
        steps=(
            GateStep("playwright_ai_baseline_contract", check="playwright_ai_baseline_contract"),
            GateStep(
                "playwright_bootstrap",
                (PY, "-m", "pytest", "tests/test_local_playwright_bootstrap_20260508.py", "-q"),
                live=True,
            ),
            GateStep(
                "playwright_smoke_live",
                (PY, "-m", "pytest", "tests/test_local_playwright_smoke_20260508.py", "-q"),
                live=True,
            ),
        ),
    ),
    GateModule(
        name="release_preflight",
        description="admin-web static checks and active-source secret scan",
        steps=(
            GateStep("admin_web_typecheck", check="admin_web_typecheck"),
            GateStep("admin_web_lint", check="admin_web_lint"),
            GateStep("admin_web_audit", check="admin_web_audit"),
            GateStep("local_agent_browser_runtime_rules", check="local_agent_browser_runtime_rules"),
            GateStep("active_source_secret_scan", check="active_source_secret_scan"),
        ),
    ),
    GateModule(
        name="release_runtime",
        description="sequential live server, AI browser, and remote-control readiness gate",
        steps=(
            GateStep(
                "release_runtime_gate",
                (PY, "verify_release_runtime_gate.py", "--retries", "1", "--retry-delay", "8"),
                live=True,
            ),
        ),
    ),
)


def module_names() -> list[str]:
    return [module.name for module in MODULES]


def selected_modules(names: list[str]) -> list[GateModule]:
    if not names or names == ["all"]:
        return list(MODULES)
    known = {module.name: module for module in MODULES}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError("unknown module(s): " + ", ".join(unknown))
    return [known[name] for name in names]


def iter_selected_steps(modules, *, include_live: bool):
    for module in modules:
        for step in module.steps:
            if step.live and not include_live:
                continue
            yield module, step
