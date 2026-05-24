"""Module-scoped quality gate runner.

This runner groups the repository's verification commands by functional module
so release checks can be run independently without accidentally crossing into
installer builds, Docker operations, deploys, or staged out-of-scope files.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
MODULE_GATE_PYCACHE = Path(
    os.environ.get("HAEHAN_MODULE_GATE_PYCACHE", str(Path(os.environ["TEMP"]) / "haehan_module_gate_pycache"))
)
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(MODULE_GATE_PYCACHE))
sys.pycache_prefix = str(MODULE_GATE_PYCACHE)

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
            GateStep("local_agent_browser_runtime_rules", check="local_agent_browser_runtime_rules"),
            GateStep("common_tool_runtime_baseline_contract", check="common_tool_runtime_baseline_contract"),
            GateStep("common_tool_runtime_contract", check="common_tool_runtime_contract"),
            GateStep("app_baseline_contract", check="app_baseline_contract"),
            GateStep("standard_workflow_contract", check="standard_workflow_contract"),
            GateStep("module_baseline_contract", check="module_baseline_contract"),
            GateStep("required_local_gate_wiring", check="required_local_gate_wiring"),
            GateStep("module_boundary_contract", check="module_boundary_contract"),
            GateStep("root_legacy_script_contract", check="root_legacy_script_contract"),
            GateStep("site_registry_baseline", check="site_registry_baseline"),
            GateStep("google_automation_baseline_contract", check="google_automation_baseline_contract"),
            GateStep("google_workspace_module_baseline_contract", check="google_workspace_module_baseline_contract"),
            GateStep("google_workspace_router_compatibility", check="google_workspace_router_compatibility"),
            GateStep("google_cloud_module_baseline_contract", check="google_cloud_module_baseline_contract"),
            GateStep("google_cloud_router_compatibility", check="google_cloud_router_compatibility"),
            GateStep("google_cloud_action_policy_baseline_contract", check="google_cloud_action_policy_baseline_contract"),
            GateStep("google_cloud_readonly_local_browser_dryrun", check="google_cloud_readonly_local_browser_dryrun"),
        ),
    ),
    GateModule(
        name="portable_install",
        description="portable ZIP install scripts and contract",
        steps=(
            GateStep("portable_install_baseline_contract", check="portable_install_baseline_contract"),
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
            GateStep("desktop_auth_runtime_baseline_contract", check="desktop_auth_runtime_baseline_contract"),
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
        name="backend_core",
        description="backend module boundaries, route inventory, auth/security gates",
        steps=(
            GateStep("backend_core_baseline_contract", check="backend_core_baseline_contract"),
            GateStep("approval_flow_baseline_contract", check="approval_flow_baseline_contract"),
            GateStep(
                "backend_core_py_compile",
                (
                    PY,
                    "scripts/py_compile_no_cache.py",
                    "ai_orchestrator/server.py",
                    "ai_orchestrator/router.py",
                    "ai_orchestrator/auth.py",
                    "ai_orchestrator/auth_router.py",
                    "ai_orchestrator/approval.py",
                    "ai_orchestrator/web_task_router.py",
                    "ai_orchestrator/web_task_approval_service.py",
                    "ai_orchestrator/local_agent_router.py",
                    "ai_orchestrator/local_agent_registry.py",
                    "ai_orchestrator/server/action_task_api.py",
                    "ai_orchestrator/server/local_agent_task_api.py",
                    "ai_orchestrator/server/server_egress_policy.py",
                    "ai_orchestrator/server/execution_location_guard.py",
                    "ai_orchestrator/server/external_url_blocker.py",
                    "scripts/ops/audit_backend_runtime_contract.py",
                ),
            ),
            GateStep("backend_runtime_contract", check="backend_runtime_contract"),
            GateStep(
                "backend_core_pytest",
                (
                    PY,
                    "-m",
                    "pytest",
                    "tests/test_backend_runtime_contract_gate.py",
                    "tests/test_backend_api_contract_audit_20260516.py",
                    "tests/test_backend_service_layer_task_policy_20260516.py",
                    "tests/test_backend_policy_layer_safety_registry_20260516.py",
                    "tests/test_backend_router_server_cycle_break_20260516.py",
                    "tests/test_backend_direct_dict_boundary_lock_20260516.py",
                    "tests/test_backend_operation_final_closeout_20260518.py",
                    "tests/test_server_local_agent_task_api_20260508.py",
                    "tests/test_server_action_task_api_wiring_20260509.py",
                    "tests/test_server_task_api_approval_gate_20260509.py",
                    "tests/test_server_egress_policy_20260508.py",
                    "tests/test_server_side_external_web_execution_guard_20260508.py",
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
                    "scripts/py_compile_no_cache.py",
                    "scripts/ops/audit_local_agent_e2e_flow_contract.py",
                    "tests/test_local_agent_e2e_flow_contract.py",
                ),
            ),
            GateStep(
                "local_agent_e2e_contract",
                (PY, "scripts/ops/audit_local_agent_e2e_flow_contract.py"),
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
    GateModule(
        name="release_preflight",
        description="admin-web static checks and active-source secret scan",
        steps=(
            GateStep("release_preflight_baseline_contract", check="release_preflight_baseline_contract"),
            GateStep("ui_residue_contract", check="ui_residue_contract"),
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


def _run_check_command(command: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> tuple[bool, str]:
    executable = command[0]
    if executable == "npm":
        executable = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    try:
        result = subprocess.run(
            [executable, *command[1:]],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"{command[0]} not found"
    output = redact(result.stdout or "").strip()
    tail = output[-500:].replace("\n", " | ") if output else ""
    if result.returncode == 0:
        return True, tail or "ok"
    return False, tail or f"exit_code={result.returncode}"


def check_admin_web_typecheck() -> tuple[bool, str]:
    package = ROOT / "admin-web" / "package.json"
    if not package.exists():
        return False, "admin-web/package.json missing"
    return _run_check_command(["npm", "run", "typecheck"], cwd=ROOT / "admin-web")


def check_admin_web_lint() -> tuple[bool, str]:
    package = ROOT / "admin-web" / "package.json"
    if not package.exists():
        return False, "admin-web/package.json missing"
    return _run_check_command(["npm", "run", "lint"], cwd=ROOT / "admin-web")


def check_admin_web_audit() -> tuple[bool, str]:
    package = ROOT / "admin-web" / "package.json"
    if not package.exists():
        return False, "admin-web/package.json missing"
    failures: list[str] = []
    for command in _npm_audit_commands():
        ok, report_or_message = _read_admin_web_audit_report(command)
        if not ok:
            failures.append(str(report_or_message))
            continue

        report = report_or_message
        high, critical, total = audit_vulnerability_counts(report)
        if not high and not critical:
            return True, f"production dependency audit high=0 critical=0 total={total}"

        names = audit_high_critical_names(report)
        if names == ["next"] and next_lockfile_meets_security_floor():
            return True, "production dependency audit next advisory cross-checked by lockfile floor next>=14.2.35"
        suffix = f": {', '.join(names)}" if names else ""
        failures.append(f"production dependency audit found high={high} critical={critical}{suffix}")

    return False, failures[-1] if failures else "npm audit did not run"


def _npm_audit_commands() -> list[list[str]]:
    base = ["audit", "--omit=dev", "--json", "--package-lock-only"]
    commands: list[list[str]] = []
    npm_cmd = shutil.which("npm.cmd")
    if os.name == "nt" and npm_cmd:
        commands.append(["cmd", "/c", npm_cmd, *base])
        commands.append(["powershell", "-NoProfile", "-Command", "npm " + " ".join(base)])
        commands.append([npm_cmd, *base])
    npm = shutil.which("npm")
    if npm and npm != npm_cmd:
        commands.append([npm, *base])
    commands.append(["npm", *base])
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            deduped.append(command)
    return deduped


def _npm_audit_command() -> list[str]:
    return _npm_audit_commands()[0]


def _read_admin_web_audit_report(command: list[str]) -> tuple[bool, dict | str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT / "admin-web",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=120,
        )
    except FileNotFoundError:
        return False, "npm not found"

    output = redact(result.stdout or "").strip()
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        tail = output[-500:].replace("\n", " | ") if output else f"exit_code={result.returncode}"
        return False, "npm audit returned non-json output: " + tail
    return True, report


def audit_vulnerability_counts(report: dict) -> tuple[int, int, int]:
    vulnerabilities = report.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        high = 0
        critical = 0
        total = 0
        for item in vulnerabilities.values():
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "")).lower()
            if severity:
                total += 1
            if severity == "high":
                high += 1
            elif severity == "critical":
                critical += 1
        return high, critical, total

    counts = report.get("metadata", {}).get("vulnerabilities", {})
    high = int(counts.get("high", 0))
    critical = int(counts.get("critical", 0))
    total = int(counts.get("total", 0))
    return high, critical, total


def audit_high_critical_names(report: dict) -> list[str]:
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    names = [
        str(name)
        for name, item in vulnerabilities.items()
        if isinstance(item, dict) and str(item.get("severity", "")).lower() in {"high", "critical"}
    ]
    return sorted(names)


def next_lockfile_meets_security_floor() -> bool:
    lockfile = ROOT / "admin-web" / "package-lock.json"
    package = ROOT / "admin-web" / "package.json"
    if not lockfile.exists() or not package.exists():
        return False
    try:
        lock = json.loads(lockfile.read_text(encoding="utf-8"))
        pkg = json.loads(package.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    declared = str((pkg.get("dependencies") or {}).get("next", ""))
    installed = str(((lock.get("packages") or {}).get("node_modules/next") or {}).get("version", ""))
    return declared == "14.2.35" and _version_tuple(installed) >= (14, 2, 35)


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = []
    for item in version.split(".")[:3]:
        try:
            parts.append(int(item))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def _source_contains(path: str, needles: Iterable[str]) -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    return [needle for needle in needles if needle in text]


def _is_secret_scan_excluded(path: Path) -> bool:
    rel = normalize_path(str(path.relative_to(ROOT)))
    parts = set(rel.split("/"))
    if parts & {"node_modules", ".next", "ui_dist", "logs", "tests", "__pycache__", ".claude", ".github"}:
        return True
    if rel.startswith(("docs/", "scripts/archive/", "scripts/ops/", "data/logs/", "data/cdp_profile/")):
        return True
    if rel in {"scripts/module_quality_gate.py"}:
        return True
    return False


def check_active_source_secret_scan() -> tuple[bool, str]:
    patterns = (
        re.compile(r"BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
        re.compile(r"(?i)Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]+"),
        re.compile(r"Bearer admin-token"),
    )
    suffixes = {".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".bat", ".ps1", ".sh"}
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if _is_secret_scan_excluded(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in patterns):
            hits.append(normalize_path(str(path.relative_to(ROOT))))
            if len(hits) >= 20:
                break
    if hits:
        return False, "possible active-source secret hits: " + ", ".join(hits)
    return True, "no active-source secret patterns detected"


def imports_local_agent(text: str) -> bool:
    return bool(re.search(
        r"(?m)^\s*(?:from\s+local_agent(?:\.|\s+import\b)|import\s+local_agent(?:\.|\s|$))",
        text,
    ))


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
        if rel in {
            "desktop/tray_runtime.py",
            "desktop/main_launcher.py",
            "desktop/local_server.py",
        }:
            if imports_local_agent(text):
                violations.append(f"{rel} imports local_agent outside boundary")

    if violations:
        return False, "; ".join(violations)
    return True, "desktop auth/cross-app shortcuts are blocked and runtime boundary imports are isolated"


def check_ui_residue_contract() -> tuple[bool, str]:
    try:
        from scripts import ui_residue_audit
    except ImportError:
        import ui_residue_audit

    findings = ui_residue_audit.audit()
    failed = [finding for finding in findings if finding.status == "FAIL"]
    warned = [finding for finding in findings if finding.status == "WARN"]
    if failed:
        return False, "UI residue failures: " + ", ".join(finding.path for finding in failed)
    if warned:
        return True, "UI residue audit passed with warnings: " + ", ".join(finding.path for finding in warned)
    return True, "UI residue audit passed with no warnings"


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
        "tests/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_portable_install_baseline_contract.py",
        "tests/test_release_preflight_baseline_contract.py",
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
        "scripts/ops/audit_desktop_auth_runtime_baseline_contract.py",
        "scripts/ops/audit_portable_install_baseline_contract.py",
        "scripts/ops/audit_release_preflight_baseline_contract.py",
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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


def check_site_registry_baseline() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "scripts/ops/validate_site_registry_baseline.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "official site registry covers site modules and policy fields"


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


CHECKS: dict[str, Callable[[], tuple[bool, str]]] = {
    "out_of_scope_not_staged": check_out_of_scope_not_staged,
    "forbidden_command_matrix": check_forbidden_command_matrix,
    "desktop_security_boundary": check_desktop_security_boundary,
    "desktop_auth_runtime_baseline_contract": check_desktop_auth_runtime_baseline_contract,
    "portable_install_baseline_contract": check_portable_install_baseline_contract,
    "release_preflight_baseline_contract": check_release_preflight_baseline_contract,
    "local_agent_browser_runtime_rules": check_local_agent_browser_runtime_rules,
    "common_tool_runtime_baseline_contract": check_common_tool_runtime_baseline_contract,
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
    "google_automation_baseline_contract": check_google_automation_baseline_contract,
    "google_workspace_module_baseline_contract": check_google_workspace_module_baseline_contract,
    "google_workspace_router_compatibility": check_google_workspace_router_compatibility,
    "google_cloud_module_baseline_contract": check_google_cloud_module_baseline_contract,
    "google_cloud_router_compatibility": check_google_cloud_router_compatibility,
    "google_cloud_action_policy_baseline_contract": check_google_cloud_action_policy_baseline_contract,
    "google_cloud_readonly_local_browser_dryrun": check_google_cloud_readonly_local_browser_dryrun,
    "admin_web_typecheck": check_admin_web_typecheck,
    "admin_web_lint": check_admin_web_lint,
    "admin_web_audit": check_admin_web_audit,
    "active_source_secret_scan": check_active_source_secret_scan,
    "ui_residue_contract": check_ui_residue_contract,
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
