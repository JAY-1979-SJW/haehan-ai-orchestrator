"""Dry-run audit for authenticated local-agent browser dispatch.

This script is static-only by default. It does not call the server, start a
browser, run Docker, build installers, stage files, or print secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
DOC_PATH = ROOT / "docs/design/authenticated_local_agent_dispatch_dry_run_20260523.md"
OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}
FORBIDDEN_SCRIPT_TOKENS = tuple(  # noqa: RUF005
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
        encoding="utf-8",
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


def _audit_scope(findings):
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
    return staged_oos


def _audit_auth_defaults(findings):
    docker_compose = read_text("docker-compose.yml")
    if has(r"AUTH_ENABLED:\s*[\"']true[\"']", docker_compose):
        add(findings, "PASS", "compose_auth_default", "AUTH_ENABLED true")
    else:
        add(findings, "FAIL", "compose_auth_default", "AUTH_ENABLED true not found")

    config_py = read_text("ai_orchestrator/core/config.py")
    if has(r"os\.environ\.get\(\s*[\"']AUTH_ENABLED[\"']\s*,\s*[\"']true[\"']", config_py):
        add(findings, "PASS", "config_auth_default", "default true")
    else:
        add(findings, "FAIL", "config_auth_default", "default true not found")


ROUTER_REL = "ai_orchestrator/agent_hub/router/root.py"
REGISTRATION_REL = "ai_orchestrator/agent_hub/router/registration.py"
ADMIN_OWNER_GUARD = re.compile(r"require_role\(\s*[\"']admin[\"']\s*,\s*[\"']owner[\"']\s*\)")


def _endpoint_block(text: str, router_var: str, method: str, path: str) -> str | None:
    """Return decorator + signature + body of the endpoint, or None.

    The block ends at the next top-level decorator/def/class, so a guard on a
    different endpoint can never satisfy this endpoint.
    """
    deco = re.compile(
        rf"^@{re.escape(router_var)}\.{method}\(\s*[\"']{re.escape(path)}[\"']",
        re.M,
    )
    m = deco.search(text)
    if not m:
        return None
    nxt = re.compile(r"^(?:@|def |async def |class )", re.M)
    start = m.end()
    pos = start
    seen_def = False
    for nm in nxt.finditer(text, start):
        if nm.group(0).startswith("@"):
            if seen_def:
                pos = nm.start()
                break
            continue
        if not seen_def:
            seen_def = True
            continue
        pos = nm.start()
        break
    else:
        pos = len(text)
    return text[m.start() : pos]


def _audit_router(findings, router=None, registration=None):
    if router is None:
        router = read_text(ROUTER_REL)
    if registration is None:
        registration = read_text(REGISTRATION_REL)
    rv = "registration_router"

    def guarded(path: str, func: str | None = None) -> bool:
        block = _endpoint_block(registration, rv, "post", path)
        if block is None:
            return False
        if func is not None and not has(rf"^(?:async\s+)?def\s+{func}\(", block, re.M):
            return False
        return ADMIN_OWNER_GUARD.search(block) is not None

    if guarded("/register", "register_local_agent"):
        add(findings, "PASS", "register_endpoint_auth", "admin/owner required")
    else:
        add(findings, "FAIL", "register_endpoint_auth", "admin/owner guard not found")

    issue_guarded = guarded("/registration-codes")
    exchange = _endpoint_block(registration, rv, "post", "/register-with-code") is not None
    if issue_guarded and exchange:
        add(findings, "PASS", "registration_code_flow", "issue (admin/owner) and exchange endpoints present")
    else:
        add(findings, "FAIL", "registration_code_flow", "registration-code endpoints incomplete or issue unguarded")

    if has(r"^\s*local_agent_router\.include_router\(\s*_?registration_router\s*\)", router, re.M):
        add(findings, "PASS", "registration_router_included", "included in local_agent_router")
    else:
        add(findings, "FAIL", "registration_router_included", "registration_router not included")


def _audit_actions_ws(findings):
    actions = read_text("ai_orchestrator/contracts/local_agent_actions.py")
    risk = read_text("ai_orchestrator/agent_hub/policy/risk_policy.py")
    if "web_open_url_readonly" in actions and "web_open_url_readonly" in risk:
        add(findings, "PASS", "readonly_action_registered", "action and risk policy present")
    else:
        add(findings, "FAIL", "readonly_action_registered", "missing action or risk policy entry")

    ws = read_text("core/agent_runtime/connection/websocket_client.py")
    if "await asyncio.to_thread(process_task, task)" in ws:
        add(findings, "PASS", "ws_off_event_loop", "process_task uses asyncio.to_thread")
    else:
        add(findings, "FAIL", "ws_off_event_loop", "process_task may run inside event loop")

    live_verify = read_text("tools/verify/verify_live_browser_readonly_dispatch.py")
    if "_mask_agent_id" in live_verify and "device_token" not in live_verify:
        add(findings, "PASS", "live_verify_redaction", "agent id masked; token not referenced")
    else:
        add(findings, "FAIL", "live_verify_redaction", "masking/token contract failed")


def audit() -> AuditResult:
    findings: list[Finding] = []

    staged_oos = _audit_scope(findings)

    _audit_auth_defaults(findings)

    _audit_router(findings)

    _audit_actions_ws(findings)

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
