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
    from .module_quality_gate_checks_audit import (
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
        check_portable_install_baseline_contract,
        check_release_preflight_baseline_contract,
        check_site_registry_baseline,
        check_site_sso_subdomain_runtime_baseline,
        check_site_work_function_baseline,
        check_standard_workflow_contract,
    )
    from .module_quality_gate_checks_repo import (
        check_forbidden_command_matrix,
        check_local_agent_browser_runtime_rules,
        check_module_boundary_contract,
        check_out_of_scope_not_staged,
        check_required_local_gate_wiring,
        check_root_legacy_script_contract,
        imports_local_agent,
    )
    from .module_quality_gate_checks_web import (
        _is_secret_scan_excluded,
        audit_high_critical_names,
        audit_vulnerability_counts,
        check_active_source_secret_scan,
        check_admin_web_audit,
        check_admin_web_lint,
        check_admin_web_typecheck,
        next_lockfile_meets_security_floor,
    )
    from .module_quality_gate_common import (
        FORBIDDEN_TOKENS,
        MODULE_GATE_PYCACHE,
        OUT_OF_SCOPE,
        PY,
        ROOT,
        GateModule,
        GateStep,
        _run_check_command,
        _source_contains,
        all_steps,
        command_is_forbidden,
        command_is_pytest,
        command_text,
        find_staged_out_of_scope,
        git_staged_paths,
        normalize_path,
        redact,
        workspace_temp_root,
    )
    from .module_quality_gate_modules import (
        MODULES,
        iter_selected_steps,
        module_names,
        selected_modules,
    )
    from .module_quality_gate_runner import CHECKS, main, print_module_list, run_step
except ImportError:
    from scripts.module_quality_gate_checks_audit import (  # noqa: F401
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
        check_portable_install_baseline_contract,
        check_release_preflight_baseline_contract,
        check_site_registry_baseline,
        check_site_sso_subdomain_runtime_baseline,
        check_site_work_function_baseline,
        check_standard_workflow_contract,
    )
    from scripts.module_quality_gate_checks_repo import (  # noqa: F401
        check_forbidden_command_matrix,
        check_local_agent_browser_runtime_rules,
        check_module_boundary_contract,
        check_out_of_scope_not_staged,
        check_required_local_gate_wiring,
        check_root_legacy_script_contract,
        imports_local_agent,
    )
    from scripts.module_quality_gate_checks_web import (  # noqa: F401
        _is_secret_scan_excluded,
        audit_high_critical_names,
        audit_vulnerability_counts,
        check_active_source_secret_scan,
        check_admin_web_audit,
        check_admin_web_lint,
        check_admin_web_typecheck,
        next_lockfile_meets_security_floor,
    )
    from scripts.module_quality_gate_common import (  # noqa: F401
        FORBIDDEN_TOKENS,
        MODULE_GATE_PYCACHE,
        OUT_OF_SCOPE,
        PY,
        ROOT,
        GateModule,
        GateStep,
        _run_check_command,
        _source_contains,
        all_steps,
        command_is_forbidden,
        command_is_pytest,
        command_text,
        find_staged_out_of_scope,
        git_staged_paths,
        normalize_path,
        redact,
        workspace_temp_root,
    )
    from scripts.module_quality_gate_modules import (  # noqa: F401
        MODULES,
        iter_selected_steps,
        module_names,
        selected_modules,
    )
    from scripts.module_quality_gate_runner import CHECKS, main, print_module_list, run_step  # noqa: F401

# py alias — tests access gate.py
py = PY

if __name__ == "__main__":
    raise SystemExit(main())
