"""Module-scoped quality gate runner — 책임별 leaf 모듈 aggregator.

common/models/checks/runner 기능이 각 leaf 에 구현돼 있다.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from .module_quality_gate_common import (  # noqa: F401
    ROOT, PY, OUT_OF_SCOPE, FORBIDDEN_TOKENS, MODULE_GATE_PYCACHE,
    GateStep, GateModule,
    normalize_path, redact, command_text, command_is_forbidden, command_is_pytest,
    workspace_temp_root, _run_check_command, _source_contains,
    find_staged_out_of_scope, git_staged_paths, all_steps,
)
from .module_quality_gate_checks_web import _is_secret_scan_excluded  # noqa: F401
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
    check_site_work_function_baseline, check_google_automation_baseline_contract,
    check_google_workspace_module_baseline_contract, check_google_gmail_function_contract,
    check_google_workspace_router_compatibility, check_google_cloud_module_baseline_contract,
)
from .module_quality_gate_checks_web import (  # noqa: F401
    check_admin_web_typecheck, check_admin_web_lint,
    audit_vulnerability_counts, audit_high_critical_names,
)
from .module_quality_gate_runner import run_step, print_module_list, main  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
