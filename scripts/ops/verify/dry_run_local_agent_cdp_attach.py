"""Static dry-run gate for local-agent CDP attach safety.

This script does not start Chrome, connect to CDP, build, deploy, stage, commit,
or print secrets. It validates the local attach design and helper contracts.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}
DESIGN_DOC = ROOT / "docs" / "design" / "local_agent_cdp_attach_dry_run_20260523.md"
HELPER = ROOT / "core" / "agent_runtime" / "browser" / "cdp_attach.py"
CDP_DAEMON = ROOT / "scripts" / "browser" / "cdp" / "cdp_daemon.py"
APP_REALTIME_CHECK = ROOT / "tools" / "runtime" / "app_realtime_check.py"
CHROME_UI_MONITOR = ROOT / "scripts" / "archive" / "misc" / "chrome_ui_monitor.py"
CDP_CLIENT = ROOT / "scripts" / "browser" / "cdp_client.py"

SENSITIVE_PATTERNS = (
    re.compile(r"webSocketDebuggerUrl\s*[:=]\s*['\"]?ws://", re.I),
    re.compile(r"Authorization\s*:\s*Bearer\s+[^<\s]+", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"password\s*[=:]\s*[^<\s]{8,}", re.I),
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


def add(findings: list[Finding], status: str, item: str, detail: str) -> None:
    findings.append(Finding(status=status, item=item, detail=detail))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


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
    paths: set[str] = set()
    for line in status_lines:
        if len(line) < 4:
            continue
        if line[0] not in {" ", "?"}:
            paths.add(line[3:].strip().replace("\\", "/"))
    return paths


def check_design_doc(findings: list[Finding]) -> None:
    if not DESIGN_DOC.exists():
        add(findings, "FAIL", "design_doc", "missing")
        return
    text = _read(DESIGN_DOC)
    required = [
        "Only loopback CDP endpoints are allowed",
        "/json/version",
        "/json/list",
        "webSocketDebuggerUrl",
        "read-only",
        "dedicated Chrome profile",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        add(findings, "FAIL", "design_doc", "missing: " + ", ".join(missing))
    else:
        add(findings, "PASS", "design_doc", str(DESIGN_DOC.relative_to(ROOT)))


def check_helper_contract(findings: list[Finding]) -> None:
    if not HELPER.exists():
        add(findings, "FAIL", "cdp_attach_helper", "missing")
        return
    from core.agent_runtime.browser.cdp_attach import (
        CDPAttachValidationError,
        build_cdp_list_url,
        build_cdp_version_url,
        normalize_cdp_endpoint,
        summarize_cdp_tabs,
    )

    try:
        normalize_cdp_endpoint("192.168.0.10", 9222)
    except CDPAttachValidationError:
        add(findings, "PASS", "loopback_only", "remote host rejected")
    else:
        add(findings, "FAIL", "loopback_only", "remote host accepted")

    if build_cdp_version_url("127.0.0.1", 9222).endswith("/json/version") and build_cdp_list_url(
        "localhost", 9222
    ).endswith("/json/list"):
        add(findings, "PASS", "cdp_discovery_urls", "version/list only")
    else:
        add(findings, "FAIL", "cdp_discovery_urls", "unexpected URL contract")

    summary = summarize_cdp_tabs(
        [
            {
                "type": "page",
                "title": "Example",
                "url": "https://user:pass@example.com/path?secret=value#token",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/abc",
            }
        ]
    )
    rendered = json.dumps(summary, ensure_ascii=False)
    forbidden = ["secret=value", "#token", "user:pass", "webSocketDebuggerUrl", "ws://"]
    if any(item in rendered for item in forbidden):
        add(findings, "FAIL", "cdp_tab_redaction", "raw sensitive tab data exposed")
    elif summary["tabs"][0]["url"]["has_query"] and summary["tabs"][0]["url"]["has_credentials"]:
        add(findings, "PASS", "cdp_tab_redaction", "raw query/credentials/websocket omitted")
    else:
        add(findings, "FAIL", "cdp_tab_redaction", "summary flags missing")


def check_existing_sources(findings: list[Finding]) -> None:
    daemon = _read(CDP_DAEMON) if CDP_DAEMON.exists() else ""
    realtime = _read(APP_REALTIME_CHECK) if APP_REALTIME_CHECK.exists() else ""

    if "--remote-debugging-port" in daemon and "PROFILE_DIR" in daemon and "cdp_profile" in daemon:
        add(findings, "PASS", "dedicated_cdp_profile", "cdp_daemon has dedicated profile launch")
    else:
        add(findings, "FAIL", "dedicated_cdp_profile", "daemon profile launch not identified")

    if "/json/version" in realtime and "/json/list" in realtime:
        add(findings, "PASS", "readonly_discovery_endpoints", "realtime check uses version/list")
    else:
        add(findings, "FAIL", "readonly_discovery_endpoints", "version/list not identified")

    monitor_text = _read(CHROME_UI_MONITOR) if CHROME_UI_MONITOR.exists() else ""
    client_text = _read(CDP_CLIENT) if CDP_CLIENT.exists() else ""
    archive_state_literal = '"data" / "chrome_ui_monitor_state.json"'
    runtime_state_literal = '"data" / "runtime" / "chrome_ui_monitor_state.json"'
    if archive_state_literal in monitor_text or archive_state_literal in client_text:
        add(findings, "FAIL", "chrome_ui_monitor_runtime_path", "archive/data state path remains active")
    elif runtime_state_literal in monitor_text and runtime_state_literal in client_text:
        add(findings, "PASS", "chrome_ui_monitor_runtime_path", "uses data/runtime state path")
    else:
        add(findings, "FAIL", "chrome_ui_monitor_runtime_path", "runtime state path not identified")

    forbidden_runtime = ["Network.getAllCookies", "Storage.get", "Storage.clearDataForOrigin"]
    helper_text = _read(HELPER) if HELPER.exists() else ""
    offenders = [needle for needle in forbidden_runtime if needle in helper_text]
    if offenders:
        add(findings, "FAIL", "helper_forbidden_cdp_methods", ", ".join(offenders))
    else:
        add(findings, "PASS", "helper_forbidden_cdp_methods", "none")


def dry_run() -> DryRunResult:
    findings: list[Finding] = []
    status_lines = git_status_short()
    staged_oos = sorted(staged_paths(status_lines) & OUT_OF_SCOPE)
    if staged_oos:
        add(findings, "FAIL", "out_of_scope_staged", ", ".join(staged_oos))
    else:
        add(findings, "PASS", "out_of_scope_staged", "none")

    check_design_doc(findings)
    check_helper_contract(findings)
    check_existing_sources(findings)

    rendered = "\n".join(f"{item.status} {item.item} {item.detail}" for item in findings)
    if any(pattern.search(rendered) for pattern in SENSITIVE_PATTERNS):
        add(findings, "FAIL", "dry_run_secret_output", "secret-shaped output detected")
    else:
        add(findings, "PASS", "dry_run_secret_output", "no secret-shaped output")

    fail_count = sum(1 for finding in findings if finding.status == "FAIL")
    if staged_oos:
        verdict = "FAIL_OUT_OF_SCOPE_MUTATED"
    elif fail_count:
        verdict = "FAIL_LOCAL_AGENT_CDP_ATTACH_DRY_RUN"
    else:
        verdict = "PASS_LOCAL_AGENT_CDP_ATTACH_DRY_RUN_READY"
    return DryRunResult(verdict=verdict, passed=fail_count == 0, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = dry_run()
    payload = {
        "verdict": result.verdict,
        "passed": result.passed,
        "findings": [finding.__dict__ for finding in result.findings],
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
