"""Dry-run gate for manual local-agent browser smoke.

This validates that the manual smoke path can be run safely later, without
performing network calls, starting a local agent, launching a browser, editing
server users, or printing secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}
REQUIRED_FILES = (
    "docs/design/authenticated_local_agent_dispatch_dry_run_20260523.md",
    "tools/audits/agent/audit_authed_local_agent_dispatch_dry_run.py",
    "tools/verify/verify_live_browser_readonly_dispatch.py",
    "core/agent_runtime/agent.py",
    "core/agent_runtime/connection/websocket_client.py",
    "core/agent_runtime/browser/browser_readonly_runtime.py",
    "ai_orchestrator/agent_hub/router/root.py",
    "ai_orchestrator/contracts/local_agent_actions.py",
    "ai_orchestrator/agent_hub/policy/risk_policy.py",
)
SENSITIVE_PATTERNS = (
    re.compile(r"Authorization\s*:\s*Bearer\s+[^<\s]+", re.I),
    re.compile(r"device_token\s*=\s*[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"registration_code\s*=\s*[A-Za-z0-9-]{8,}", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
)


@dataclass
class Finding:
    status: str
    item: str
    detail: str


@dataclass
class DryRunResult:
    verdict: str
    passed: bool
    findings: list[Finding] = field(default_factory=list)


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def add(findings: list[Finding], status: str, item: str, detail: str) -> None:
    findings.append(Finding(status, item, detail))


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
        if line[0] not in {" ", "?"}:
            staged.add(line[3:].strip().replace("\\", "/"))
    return staged


def _dry_run_files_router(findings):
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        add(findings, "FAIL", "required_files", ", ".join(missing))
    else:
        add(findings, "PASS", "required_files", "all present")

    # 등록 라우트는 local_agent_router_registration.py 로 분리됨 — 분리 전/후 두 파일을 함께 읽는다.
    router = "\n".join(
        read(rel)
        for rel in (
            "ai_orchestrator/agent_hub/router/root.py",
            "ai_orchestrator/agent_hub/router/registration.py",
        )
        if (ROOT / rel).exists()
    )
    has_issue_endpoint = any(
        f'@{name}.post("/registration-codes")' in router for name in ("local_agent_router", "registration_router")
    )
    if 'require_role("admin", "owner")' in router and has_issue_endpoint:
        add(findings, "PASS", "authenticated_registration_code_flow", "admin/owner issue endpoint present")
    else:
        add(findings, "FAIL", "authenticated_registration_code_flow", "guard or endpoint missing")


def _dry_run_config_actions(findings):
    config = read("ai_orchestrator/core/config.py")
    compose = read("docker-compose.yml")
    if 'os.environ.get("AUTH_ENABLED", "true")' in config and 'AUTH_ENABLED: "true"' in compose:
        add(findings, "PASS", "auth_fail_closed_defaults", "config and compose default true")
    else:
        add(findings, "FAIL", "auth_fail_closed_defaults", "AUTH_ENABLED true defaults missing")

    actions = read("ai_orchestrator/contracts/local_agent_actions.py")
    risk = read("ai_orchestrator/agent_hub/policy/risk_policy.py")
    if "web_open_url_readonly" in actions and "web_open_url_readonly" in risk:
        add(findings, "PASS", "readonly_action_allowed", "registered in action and risk policy")
    else:
        add(findings, "FAIL", "readonly_action_allowed", "missing readonly browser action")


def _dry_run_ws_verifier(findings):
    ws = read("core/agent_runtime/connection/websocket_client.py")
    if "await asyncio.to_thread(process_task, task)" in ws:
        add(findings, "PASS", "playwright_off_event_loop", "process_task uses to_thread")
    else:
        add(findings, "FAIL", "playwright_off_event_loop", "sync browser may run inside event loop")

    verifier = read("tools/verify/verify_live_browser_readonly_dispatch.py")
    if "_mask_agent_id" in verifier and "device_token" not in verifier:
        add(findings, "PASS", "live_verifier_redaction", "agent id masked and no token reference")
    else:
        add(findings, "FAIL", "live_verifier_redaction", "redaction contract missing")


def _dry_run_no_side_effects(findings):
    this_script = Path(__file__).read_text(encoding="utf-8", errors="replace")
    forbidden_runtime = tuple(
        "".join(parts)
        for parts in (
            ("url", "open", "("),
            ("subprocess", ".", "Popen", "("),
            ("web", "browser", "."),
        )
    ) + tuple(
        " ".join(parts)
        for parts in (
            ("docker", "compose"),
            ("git", "push"),
            ("npm", "run", "build"),
        )
    )
    hits = [token for token in forbidden_runtime if token in this_script]
    if hits:
        add(findings, "FAIL", "dry_run_no_runtime_side_effects", ", ".join(hits))
    else:
        add(findings, "PASS", "dry_run_no_runtime_side_effects", "no network/process/build/deploy call")


def dry_run() -> DryRunResult:
    findings: list[Finding] = []

    status = git_status_short()
    staged_oos = sorted(staged_paths(status) & OUT_OF_SCOPE)
    if staged_oos:
        add(findings, "FAIL", "out_of_scope_staged", ", ".join(staged_oos))
    else:
        add(findings, "PASS", "out_of_scope_staged", "none")

    _dry_run_files_router(findings)

    _dry_run_config_actions(findings)

    _dry_run_ws_verifier(findings)

    _dry_run_no_side_effects(findings)

    rendered = "\n".join(f"{f.status} {f.item} {f.detail}" for f in findings)
    if any(pattern.search(rendered) for pattern in SENSITIVE_PATTERNS):
        add(findings, "FAIL", "dry_run_secret_output", "secret-shaped output detected")
    else:
        add(findings, "PASS", "dry_run_secret_output", "no secret-shaped output")

    fail_count = sum(1 for finding in findings if finding.status == "FAIL")
    if staged_oos:
        verdict = "FAIL_OUT_OF_SCOPE_MUTATED"
    elif fail_count:
        verdict = "FAIL_MANUAL_LOCAL_AGENT_BROWSER_SMOKE_DRY_RUN"
    else:
        verdict = "PASS_MANUAL_LOCAL_AGENT_BROWSER_SMOKE_DRY_RUN_READY"
    return DryRunResult(verdict=verdict, passed=fail_count == 0, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = dry_run()
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
