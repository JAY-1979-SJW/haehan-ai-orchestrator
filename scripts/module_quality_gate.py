"""Module-scoped quality gate runner — 책임별 leaf 모듈 aggregator.

common/models/checks/runner 기능이 각 leaf 에 구현돼 있다.
직접 실행(`python scripts/module_quality_gate.py`) 또는
패키지 import(`import scripts.module_quality_gate`) 양쪽 모두 지원.
[docs/module_separation_standard.md]
"""
from __future__ import annotations
import os  # noqa: F401 — tests access gate.os
import shutil  # noqa: F401 — tests access gate.shutil
import subprocess  # noqa: F401 — tests access gate.subprocess

# 직접 실행 시 sys.path에 scripts/ 부모를 추가하여 상대 import를 절대 import로 대체
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

try:
    from .module_quality_gate_common import (  # noqa: F401
        ROOT, PY, OUT_OF_SCOPE, FORBIDDEN_TOKENS, MODULE_GATE_PYCACHE,
        GateStep, GateModule,
        normalize_path, redact, command_text, command_is_forbidden, command_is_pytest,
        workspace_temp_root, _run_check_command, _source_contains,
        find_staged_out_of_scope, git_staged_paths, all_steps,
    )
    from .module_quality_gate_modules import (  # noqa: F401
        MODULES, module_names, selected_modules, iter_selected_steps,
    )
    from .module_quality_gate_checks_repo import (  # noqa: F401
        imports_local_agent,
        check_out_of_scope_not_staged, check_forbidden_command_matrix,
        check_desktop_security_boundary, check_local_agent_browser_runtime_rules,
        check_required_local_gate_wiring, check_module_boundary_contract,
        check_root_legacy_script_contract,
    )
    from .module_quality_gate_checks_audit import (  # noqa: F401
        check_site_registry_baseline, check_site_sso_subdomain_runtime_baseline,
        check_site_work_function_baseline,
        check_google_automation_baseline_contract,
        check_google_workspace_module_baseline_contract,
        check_google_gmail_function_contract,
        check_google_workspace_router_compatibility,
        check_google_cloud_module_baseline_contract,
        check_google_cloud_router_compatibility,
        check_google_cloud_action_policy_baseline_contract,
        check_google_cloud_readonly_local_browser_dryrun,
        check_google_domain_module_boundaries,
        check_common_tool_runtime_contract,
        check_common_tool_runtime_baseline_contract,
        check_common_engine_commercialization_baseline,
        check_local_agent_connection_recovery_baseline,
        check_desktop_auth_runtime_baseline_contract,
        check_portable_install_baseline_contract,
        check_release_preflight_baseline_contract,
        check_app_baseline_contract,
        check_standard_workflow_contract,
        check_module_baseline_contract,
        check_backend_runtime_contract,
        check_backend_core_baseline_contract,
        check_local_agent_e2e_baseline_contract,
        check_approval_flow_baseline_contract,
        check_playwright_ai_baseline_contract,
    )
    from .module_quality_gate_checks_web import (  # noqa: F401
        check_admin_web_typecheck, check_admin_web_lint, check_admin_web_audit,
        audit_vulnerability_counts, audit_high_critical_names,
        _is_secret_scan_excluded, next_lockfile_meets_security_floor,
        check_active_source_secret_scan, check_ui_residue_contract,
    )
    from .module_quality_gate_runner import run_step, print_module_list, main, CHECKS  # noqa: F401
except ImportError:
    from scripts.module_quality_gate_common import (  # noqa: F401
        ROOT, PY, OUT_OF_SCOPE, FORBIDDEN_TOKENS, MODULE_GATE_PYCACHE,
        GateStep, GateModule,
        normalize_path, redact, command_text, command_is_forbidden, command_is_pytest,
        workspace_temp_root, _run_check_command, _source_contains,
        find_staged_out_of_scope, git_staged_paths, all_steps,
    )
    from scripts.module_quality_gate_modules import (  # noqa: F401
        MODULES, module_names, selected_modules, iter_selected_steps,
    )
    from scripts.module_quality_gate_checks_repo import (  # noqa: F401
        imports_local_agent,
        check_out_of_scope_not_staged, check_forbidden_command_matrix,
        check_desktop_security_boundary, check_local_agent_browser_runtime_rules,
        check_required_local_gate_wiring, check_module_boundary_contract,
        check_root_legacy_script_contract,
    )
    from scripts.module_quality_gate_checks_audit import (  # noqa: F401
        check_site_registry_baseline, check_site_sso_subdomain_runtime_baseline,
        check_site_work_function_baseline,
        check_google_automation_baseline_contract,
        check_google_workspace_module_baseline_contract,
        check_google_gmail_function_contract,
        check_google_workspace_router_compatibility,
        check_google_cloud_module_baseline_contract,
        check_google_cloud_router_compatibility,
        check_google_cloud_action_policy_baseline_contract,
        check_google_cloud_readonly_local_browser_dryrun,
        check_google_domain_module_boundaries,
        check_common_tool_runtime_contract,
        check_common_tool_runtime_baseline_contract,
        check_common_engine_commercialization_baseline,
        check_local_agent_connection_recovery_baseline,
        check_desktop_auth_runtime_baseline_contract,
        check_portable_install_baseline_contract,
        check_release_preflight_baseline_contract,
        check_app_baseline_contract,
        check_standard_workflow_contract,
        check_module_baseline_contract,
        check_backend_runtime_contract,
        check_backend_core_baseline_contract,
        check_local_agent_e2e_baseline_contract,
        check_approval_flow_baseline_contract,
        check_playwright_ai_baseline_contract,
    )
    from scripts.module_quality_gate_checks_web import (  # noqa: F401
        check_admin_web_typecheck, check_admin_web_lint, check_admin_web_audit,
        audit_vulnerability_counts, audit_high_critical_names,
        _is_secret_scan_excluded, next_lockfile_meets_security_floor,
        check_active_source_secret_scan, check_ui_residue_contract,
    )
    from scripts.module_quality_gate_runner import run_step, print_module_list, main, CHECKS  # noqa: F401

# py alias — tests access gate.py
py = PY  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
