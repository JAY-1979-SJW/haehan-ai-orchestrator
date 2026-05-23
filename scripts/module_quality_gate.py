"""Module-scoped quality gate runner.

This runner groups the repository's verification commands by functional module
so release checks can be run independently without accidentally crossing into
installer builds, Docker operations, deploys, or staged out-of-scope files.
"""
from __future__ import annotations

import argparse
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
        ),
    ),
    GateModule(
        name="portable_install",
        description="portable ZIP install scripts and contract",
        steps=(
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
        name="playwright_ai",
        description="local Playwright bootstrap and AI proxy no-secret contract",
        steps=(
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
    command = _npm_audit_command()
    ok, report_or_message = _read_admin_web_audit_report(command)
    if not ok:
        return False, str(report_or_message)

    report = report_or_message
    high, critical, total = audit_vulnerability_counts(report)
    if high or critical:
        retry_ok, retry_report_or_message = _read_admin_web_audit_report(command)
        if not retry_ok:
            return False, str(retry_report_or_message)
        retry_report = retry_report_or_message
        retry_high, retry_critical, retry_total = audit_vulnerability_counts(retry_report)
        if not retry_high and not retry_critical:
            return True, f"production dependency audit high=0 critical=0 total={retry_total} after retry"
        high, critical, total = retry_high, retry_critical, retry_total
        report = retry_report
        names = audit_high_critical_names(report)
        suffix = f": {', '.join(names)}" if names else ""
        return False, f"production dependency audit found high={high} critical={critical}{suffix}"
    return True, f"production dependency audit high=0 critical=0 total={total}"


def _npm_audit_command() -> list[str]:
    npm_cmd = shutil.which("npm.cmd")
    if os.name == "nt" and npm_cmd:
        return ["cmd", "/c", npm_cmd, "audit", "--omit=dev", "--json", "--package-lock-only"]
    executable = npm_cmd or shutil.which("npm") or "npm"
    return [executable, "audit", "--omit=dev", "--json", "--package-lock-only"]


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


CHECKS: dict[str, Callable[[], tuple[bool, str]]] = {
    "out_of_scope_not_staged": check_out_of_scope_not_staged,
    "forbidden_command_matrix": check_forbidden_command_matrix,
    "desktop_security_boundary": check_desktop_security_boundary,
    "local_agent_browser_runtime_rules": check_local_agent_browser_runtime_rules,
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
