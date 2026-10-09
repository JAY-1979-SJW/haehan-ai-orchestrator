"""Repository-owned required quality gate.

This replaces GitHub Actions for the locked local-agent browser runtime checks.
It is designed for local pre-commit/pre-push execution and does not build,
deploy, push, run Docker, or start browsers.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

# 직접 실행에서도 scripts 패키지를 찾게 한다
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.app_paths import repo_root
from scripts.common.runtime_temp import usable_temp_base
from tools.quality.module_quality_gate_common import redact

ROOT = repo_root()
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30
PYTEST_FLAGS = ("-p", "no:cacheprovider", "-q")

COMMANDS: tuple[tuple[str, ...], ...] = (
    (
        sys.executable,
        "-m",
        "py_compile",
        "core/agent_runtime/browser/cdp_attach.py",
        "scripts/archive/misc/chrome_ui_monitor.py",
        "scripts/browser/cdp_client.py",
        "tools/verify/dry_run_local_agent_cdp_attach.py",
        "tools/audits/agent/audit_common_tool_runtime.py",
        "tools/audits/agent/audit_common_tool_runtime_baseline_contract.py",
        "tools/audits/app/audit_common_engine_commercialization_baseline.py",
        "tools/audits/agent/audit_local_agent_connection_recovery_baseline.py",
        "tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py",
        "tools/audits/agent/audit_local_agent_e2e_flow_contract.py",
        "tools/audits/app/audit_app_baseline_contract.py",
        "tools/audits/app/audit_standard_workflow_contract.py",
        "tools/audits/app/audit_module_baseline_contract.py",
        "tools/audits/backend/audit_backend_core_baseline_contract.py",
        "tools/audits/agent/audit_local_agent_e2e_baseline_contract.py",
        "tools/audits/app/audit_approval_flow_baseline_contract.py",
        "tools/audits/agent/audit_playwright_ai_baseline_contract.py",
        "tools/audits/app/audit_module_boundaries.py",
        "tools/repo_gates/audit_root_legacy_scripts.py",
        "scripts/google/audit_gmail_function_contract.py",
        "tools/audits/google/audit_google_home_login_gate.py",
        "tools/audits/google/audit_google_automation_baseline_contract.py",
        "tools/audits/app/audit_site_sso_subdomain_runtime_baseline.py",
        "tools/audits/app/audit_site_work_function_baseline.py",
        "tools/audits/app/audit_ai_agent_app_structure_design_baseline.py",
        "tools/audits/app/audit_ai_agent_ui_structure_blueprint.py",
        "tools/audits/agent/audit_mcp_gateway_baseline.py",
        "scripts/common/ai_work_session.py",
        "tools/audits/app/audit_ai_work_session_gate.py",
        "scripts/google/common/gmail_analysis.py",
        "scripts/google/ads_signup.py",
        "scripts/google/live_surface_explorer.py",
        "scripts/google/cloud/live_console_explorer.py",
        "scripts/google/ai_usage_labels.py",
        "scripts/google/android_app_dev_labels.py",
        "scripts/google/android_app_dev_report.py",
        "scripts/google/common/domain_taxonomy.py",
        "scripts/google/managed_console.py",
        "scripts/google/precision_report.py",
        "scripts/google/common/subdomain_logic.py",
        "scripts/google/common/tab_logic.py",
        "scripts/common/gates/work_mode_gate.py",
        "scripts/google/workspace_basic.py",
        "scripts/google/youtube/search.py",
        "scripts/google/common/youtube_upload.py",
        "scripts/youtube/oauth.py",
        "scripts/youtube/research.py",
        "scripts/youtube/router.py",
        "core/agent_runtime/runtime/common_tool_runtime.py",
        "tools/quality/module_quality_gate.py",
        "tests/test_common_tool_runtime.py",
        "tests/app_contracts/test_common_tool_runtime_baseline_contract.py",
        "tests/app_contracts/test_common_engine_commercialization_baseline.py",
        "tests/desktop/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_local_agent_e2e_flow_contract.py",
        "tests/app_contracts/test_app_baseline_contract.py",
        "tests/app_contracts/test_standard_workflow_contract.py",
        "tests/app_contracts/test_module_baseline_contract.py",
        "tests/app_contracts/test_backend_core_baseline_contract.py",
        "tests/test_local_agent_e2e_baseline_contract.py",
        "tests/approval/test_approval_flow_baseline_contract.py",
        "tests/app_contracts/test_playwright_ai_baseline_contract.py",
        "tests/test_local_agent_browser_runtime_operating_rules.py",
        "tests/test_local_agent_cdp_attach.py",
        "tests/test_dry_run_local_agent_cdp_attach.py",
        "tests/quality_gates/test_module_quality_gate.py",
        "tests/quality_gates/test_required_quality_gate.py",
        "tests/quality_gates/test_module_boundaries.py",
        "tests/quality_gates/test_root_legacy_scripts_audit.py",
        "tests/google/test_google_gmail_function_contract.py",
        "tests/google/test_google_gmail_analysis.py",
        "tests/google/test_google_ads_signup.py",
        "tests/google/test_google_live_surface_explorer.py",
        "tests/google/test_google_cloud_live_console_explorer.py",
        "tests/google/test_google_ai_usage_labels.py",
        "tests/google/test_google_android_app_dev.py",
        "tests/google/test_google_domain_taxonomy.py",
        "tests/google/test_google_managed_console.py",
        "tests/google/test_google_work_mode_gate.py",
        "tests/google/test_google_workspace_basic.py",
        "tests/google/test_google_youtube_search.py",
        "tests/google/test_google_youtube_upload.py",
        "tests/google/test_google_precision_report.py",
        "tests/google/test_google_subdomain_logic.py",
        "tests/google/test_google_tab_logic.py",
        "tests/site_engine/test_site_sso_subdomain_runtime.py",
        "tests/site_engine/test_site_work_function_baseline.py",
        "tests/quality_gates/test_ai_agent_app_structure_design_baseline.py",
        "tests/quality_gates/test_ai_agent_ui_structure_blueprint.py",
        "tests/server_core/test_mcp_gateway_baseline.py",
        "tests/quality_gates/test_ai_work_session_gate.py",
        "tests/youtube/test_youtube_oauth.py",
        "tests/youtube/test_youtube_research.py",
    ),
    (sys.executable, "tools/verify/dry_run_local_agent_cdp_attach.py"),
    (sys.executable, "tools/audits/agent/audit_common_tool_runtime.py"),
    (sys.executable, "tools/audits/agent/audit_common_tool_runtime_baseline_contract.py"),
    (sys.executable, "tools/audits/app/audit_common_engine_commercialization_baseline.py"),
    (sys.executable, "tools/audits/agent/audit_local_agent_connection_recovery_baseline.py"),
    (sys.executable, "tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py"),
    (sys.executable, "tools/audits/agent/audit_local_agent_e2e_flow_contract.py"),
    (sys.executable, "tools/audits/app/audit_app_baseline_contract.py"),
    (sys.executable, "tools/audits/app/audit_standard_workflow_contract.py"),
    (sys.executable, "tools/audits/app/audit_module_baseline_contract.py"),
    (sys.executable, "tools/audits/backend/audit_backend_core_baseline_contract.py"),
    (sys.executable, "tools/audits/agent/audit_local_agent_e2e_baseline_contract.py"),
    (sys.executable, "tools/audits/app/audit_approval_flow_baseline_contract.py"),
    (sys.executable, "tools/audits/agent/audit_playwright_ai_baseline_contract.py"),
    (sys.executable, "tools/audits/app/audit_module_boundaries.py"),
    (sys.executable, "tools/repo_gates/audit_root_legacy_scripts.py"),
    (sys.executable, "scripts/google/audit_gmail_function_contract.py"),
    (sys.executable, "tools/audits/google/audit_google_home_login_gate.py"),
    (sys.executable, "tools/audits/google/audit_google_automation_baseline_contract.py"),
    (sys.executable, "tools/audits/app/audit_site_sso_subdomain_runtime_baseline.py"),
    (sys.executable, "tools/audits/app/audit_site_work_function_baseline.py"),
    (sys.executable, "tools/audits/app/audit_ai_agent_app_structure_design_baseline.py"),
    (sys.executable, "tools/audits/app/audit_ai_agent_ui_structure_blueprint.py"),
    (sys.executable, "tools/audits/agent/audit_mcp_gateway_baseline.py"),
    (sys.executable, "tools/audits/app/audit_ai_work_session_gate.py"),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_common_tool_runtime.py",
        "tests/app_contracts/test_common_tool_runtime_baseline_contract.py",
        "tests/app_contracts/test_common_engine_commercialization_baseline.py",
        "tests/desktop/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_local_agent_e2e_flow_contract.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/app_contracts/test_app_baseline_contract.py",
        "tests/app_contracts/test_standard_workflow_contract.py",
        "tests/app_contracts/test_module_baseline_contract.py",
        "tests/app_contracts/test_backend_core_baseline_contract.py",
        "tests/test_local_agent_e2e_baseline_contract.py",
        "tests/approval/test_approval_flow_baseline_contract.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_local_agent_connection_recovery_baseline.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/app_contracts/test_playwright_ai_baseline_contract.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_local_agent_browser_runtime_operating_rules.py",
        "tests/test_local_agent_cdp_attach.py",
        "tests/test_dry_run_local_agent_cdp_attach.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/quality_gates/test_required_quality_gate.py",
        "tests/quality_gates/test_module_boundaries.py",
        "tests/quality_gates/test_root_legacy_scripts_audit.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/google/test_google_gmail_function_contract.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/google/test_google_gmail_analysis.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/google/test_google_home_login_gate.py",
        "tests/google/test_google_ads_signup.py",
        "tests/google/test_google_workspace_basic.py",
        "tests/google/test_google_youtube_search.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/google/test_google_subdomain_logic.py",
        "tests/google/test_google_tab_logic.py",
        "tests/google/test_google_live_surface_explorer.py",
        "tests/google/test_google_cloud_live_console_explorer.py",
        "tests/google/test_google_ai_usage_labels.py",
        "tests/google/test_google_android_app_dev.py",
        "tests/google/test_google_domain_taxonomy.py",
        "tests/google/test_google_managed_console.py",
        "tests/google/test_google_work_mode_gate.py",
        "tests/google/test_google_youtube_upload.py",
        "tests/google/test_google_precision_report.py",
        "tests/site_engine/test_site_sso_subdomain_runtime.py",
        "tests/youtube/test_youtube_oauth.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/youtube/test_youtube_research.py",
        *PYTEST_FLAGS,
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "tests/site_engine/test_site_work_function_baseline.py",
        "tests/quality_gates/test_ai_agent_app_structure_design_baseline.py",
        "tests/quality_gates/test_ai_agent_ui_structure_blueprint.py",
        "tests/server_core/test_mcp_gateway_baseline.py",
        "tests/quality_gates/test_ai_work_session_gate.py",
        *PYTEST_FLAGS,
    ),
    (sys.executable, "tools/quality/module_quality_gate.py", "--module", "repo_guard"),
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


def command_text(command: tuple[str, ...]) -> str:
    return " ".join(command)


def command_is_forbidden(command: tuple[str, ...]) -> bool:
    lowered = command_text(command).lower()
    return any(token in lowered for token in FORBIDDEN_COMMAND_TOKENS)


def command_is_pytest(command: tuple[str, ...]) -> bool:
    return "-m" in command and "pytest" in command


def command_needs_isolated_pytest_temp(command: tuple[str, ...]) -> bool:
    return command_is_pytest(command)


def command_timeout_seconds() -> int:
    raw = os.environ.get("HAEHAN_REQUIRED_GATE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_COMMAND_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_COMMAND_TIMEOUT_SECONDS
    return max(1, value)


def command_timeout_for(command: tuple[str, ...]) -> int:
    timeout_s = command_timeout_seconds()
    if (
        len(command) >= 4
        and command[1].endswith("tools/quality/module_quality_gate.py")
        and "--module" in command
        and "repo_guard" in command
    ):
        return max(timeout_s, 240)
    return timeout_s


def command_with_runtime_args(command: tuple[str, ...]) -> tuple[str, ...]:
    return command


def isolated_pytest_temp(env: dict[str, str]) -> Path:
    base = usable_temp_base("required_gate_temp", "HAEHAN_REQUIRED_GATE_TEMP")
    target = base / uuid4().hex
    return target


def run_command(command: tuple[str, ...]) -> GateResult:
    name = command_text(command)
    if command_is_forbidden(command):
        return GateResult(name=name, ok=False, detail="forbidden command blocked")

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    use_isolated_pytest_temp = command_needs_isolated_pytest_temp(command)
    if use_isolated_pytest_temp:
        env.pop("PYTHONPYCACHEPREFIX", None)
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        temp_root = isolated_pytest_temp(env)
        env["TMP"] = str(temp_root)
        env["TEMP"] = str(temp_root)
        env["TMPDIR"] = str(temp_root)
    else:
        pycache = Path(
            env.get(
                "HAEHAN_REQUIRED_GATE_PYCACHE",
                str(Path(env.get("TEMP", str(ROOT / "tmp"))) / "haehan_required_gate_pycache"),
            )
        )
        pycache.mkdir(parents=True, exist_ok=True)
        env.setdefault("PYTHONPYCACHEPREFIX", str(pycache))

    timeout_s = command_timeout_for(command)
    is_pytest = command_is_pytest(command)
    runtime_command = list(command_with_runtime_args(command))
    try:
        result = subprocess.run(
            runtime_command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            text=True,
            stdout=None if is_pytest else subprocess.PIPE,
            stderr=None if is_pytest else subprocess.STDOUT,
            check=False,
            env=env,
            timeout=timeout_s,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired as exc:
        output = redact((exc.stdout or exc.stderr or "") if isinstance(exc.stdout or exc.stderr, str) else "").strip()
        if output:
            print(output)
        return GateResult(name=name, ok=False, detail=f"timeout_after={timeout_s}s")

    if not is_pytest:
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
