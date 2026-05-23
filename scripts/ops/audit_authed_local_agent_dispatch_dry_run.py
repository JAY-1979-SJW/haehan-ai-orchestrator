"""Dry-run audit for authenticated local-agent browser dispatch.

This script is static-only by default. It does not call the server, start a
browser, run Docker, build installers, stage files, or print secrets.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "docs/design/authenticated_local_agent_dispatch_dry_run_20260523.md"
OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}
FORBIDDEN_SCRIPT_TOKENS = tuple(
    " ".join(parts)
    for parts in (
        ("docker", "compose", "up"),
        ("docker", "build"),
        ("git", "add"),
        ("git", "commit"),
        ("git", "push"),
        ("npm", "run", "build"),
    )
) + (f"electron{chr(45)}builder", "py" + "installer")
SENSITIVE_OUTPUT_PATTERNS = (
    re.compile(r"device_token\s*[=:]"),
    re.compile(r"registration_code\s*[=:]"),
    re.compile(r"Authorization\s*:\s*Bearer\s+[^<\s]+", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
)


@dataclass
class Finding:
    status: str
    item: str
    detail: str


@dataclass
class AuditResult:
    verdict: str
    passed: bool
    findings: list[Finding] = field(default_factory=list)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def add(findings: list[Finding], status: str, item: str, detail: str) -> None:
    findings.append(Finding(status=status, item=item, detail=detail))


def has(pattern: str, text: str, flags: int = 0) -> bool:
    return re.search(pattern, text, flags) is not None


def git_status_short() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return ["!! git status failed"]
    return [line.rstrip() for line in proc.stdout.splitlines() if line.strip()]


def staged_paths(status_lines: list[str]) -> set[str]:
    staged: set[str] = set()
    for line in status_lines:
        if len(line) < 4:
            continue
        index_status = line[0]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if index_status not in {" ", "?"}:
            staged.add(path.replace("\\", "/"))
    return staged


def audit() -> AuditResult:
    findings: list[Finding] = []

    status_lines = git_status_short()
    staged_oos = sorted(staged_paths(status_lines) & OUT_OF_SCOPE)
    if staged_oos:
        add(findings, "FAIL", "out_of_scope_staged", ", ".join(staged_oos))
    else:
        add(findings, "PASS", "out_of_scope_staged", "none")

    if DOC_PATH.exists():
        add(findings, "PASS", "design_doc_exists", _rel(DOC_PATH))
    else:
        add(findings, "FAIL", "design_doc_exists", "missing")

    docker_compose = read_text("docker-compose.yml")
    if has(r"AUTH_ENABLED:\s*[\"']true[\"']", docker_compose):
        add(findings, "PASS", "compose_auth_default", "AUTH_ENABLED true")
    else:
        add(findings, "FAIL", "compose_auth_default", "AUTH_ENABLED true not found")

    config_py = read_text("ai_orchestrator/config.py")
    if has(r"os\.environ\.get\(\s*[\"']AUTH_ENABLED[\"']\s*,\s*[\"']true[\"']", config_py):
        add(findings, "PASS", "config_auth_default", "default true")
    else:
        add(findings, "FAIL", "config_auth_default", "default true not found")

    router = read_text("ai_orchestrator/local_agent_router.py")
    protected_register = has(
        r"def\s+register_local_agent\([\s\S]{0,300}require_role\(\s*[\"']admin[\"']\s*,\s*[\"']owner[\"']\s*\)",
        router,
    )
    if protected_register:
        add(findings, "PASS", "register_endpoint_auth", "admin/owner required")
    else:
        add(findings, "FAIL", "register_endpoint_auth", "admin/owner guard not found")

    if '@local_agent_router.post("/registration-codes")' in router and '@local_agent_router.post("/register-with-code")' in router:
        add(findings, "PASS", "registration_code_flow", "issue and exchange endpoints present")
    else:
        add(findings, "FAIL", "registration_code_flow", "registration-code endpoints incomplete")

    actions = read_text("ai_orchestrator/local_agent_actions.py")
    risk = read_text("ai_orchestrator/local_agent_risk_policy.py")
    if "web_open_url_readonly" in actions and "web_open_url_readonly" in risk:
        add(findings, "PASS", "readonly_action_registered", "action and risk policy present")
    else:
        add(findings, "FAIL", "readonly_action_registered", "missing action or risk policy entry")

    ws = read_text("local_agent/websocket_client.py")
    if "await asyncio.to_thread(process_task, task)" in ws:
        add(findings, "PASS", "ws_off_event_loop", "process_task uses asyncio.to_thread")
    else:
        add(findings, "FAIL", "ws_off_event_loop", "process_task may run inside event loop")

    live_verify = read_text("verify_live_browser_readonly_dispatch.py")
    if "_mask_agent_id" in live_verify and "device_token" not in live_verify:
        add(findings, "PASS", "live_verify_redaction", "agent id masked; token not referenced")
    else:
        add(findings, "FAIL", "live_verify_redaction", "masking/token contract failed")

    script_text = Path(__file__).read_text(encoding="utf-8", errors="replace")
    forbidden = [token for token in FORBIDDEN_SCRIPT_TOKENS if token in script_text.lower()]
    if forbidden:
        add(findings, "FAIL", "dry_run_forbidden_commands", ", ".join(forbidden))
    else:
        add(findings, "PASS", "dry_run_forbidden_commands", "none")

    rendered = "\n".join(f"{f.status} {f.item} {f.detail}" for f in findings)
    leaks = [p.pattern for p in SENSITIVE_OUTPUT_PATTERNS if p.search(rendered)]
    if leaks:
        add(findings, "FAIL", "audit_output_secret_redaction", "sensitive output pattern")
    else:
        add(findings, "PASS", "audit_output_secret_redaction", "no raw secret-shaped output")

    fail_count = sum(1 for f in findings if f.status == "FAIL")
    if staged_oos:
        verdict = "FAIL_OUT_OF_SCOPE_MUTATED"
    elif fail_count:
        verdict = "FAIL_AUTHED_LOCAL_AGENT_DISPATCH_SECURITY_RISK"
    else:
        verdict = "PASS_AUTHED_LOCAL_AGENT_DISPATCH_DRY_RUN_READY"
    return AuditResult(verdict=verdict, passed=fail_count == 0, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = audit()
    payload = {
        "verdict": result.verdict,
        "passed": result.passed,
        "findings": [f.__dict__ for f in result.findings],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"verdict={result.verdict}")
        for finding in result.findings:
            print(f"[{finding.status}] {finding.item}: {finding.detail}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
