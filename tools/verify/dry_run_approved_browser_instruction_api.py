"""Dry-run gate for approved-user readonly browser instruction API.

This script runs the FastAPI router in memory through TestClient. It does not
start a server, launch a browser, call the network, deploy, build, stage files,
or print secrets.

주의(2026-09-29): local_agent_registry._reg.clear() 는 이제 실제 영속화 파일
(data/local_agent_registry_state.json — 실제 등록된 로컬 에이전트 상태)도 함께 지운다.
이 스크립트를 개발 중인 FastAPI 서버와 같은 작업 디렉터리에서 실행하면 그 상태가
지워진다 — 실행 전 로컬 에이전트가 등록돼 있다면 재등록이 필요할 수 있다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
DRY_RUN_TMP_ROOT = ROOT / "tmp" / "haehan-dry-runs"
OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}
SENSITIVE_PATTERNS = (
    re.compile(r"Authorization\s*:\s*Bearer\s+[^<\s]+", re.I),
    re.compile(r"device_token\s*[=:]\s*[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"registration_code\s*[=:]\s*[A-Za-z0-9-]{8,}", re.I),
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


def add(findings: list[Finding], status: str, item: str, detail: str) -> None:
    findings.append(Finding(status=status, item=item, detail=detail))


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


def make_client(user: dict) -> TestClient:
    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def register_agent(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/local-agents/register",
        json={"host": "dry-run-pc", "os_name": "Windows", "version": "dry-run"},
    )
    if resp.status_code != 200:
        raise AssertionError(f"register failed: {resp.status_code}")
    return str(resp.json()["agent_id"])


def _dry_run_admin_checks(findings, admin_client, agent_id):
    safe = admin_client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "Summarize the public page headings only",
            "url": "https://example.com/path?private=query",
        },
    )
    if safe.status_code == 200 and safe.json().get("action") == "web_open_url_readonly":
        add(findings, "PASS", "admin_readonly_instruction", "queued")
    else:
        add(findings, "FAIL", "admin_readonly_instruction", str(safe.status_code))

    if "private=query" in safe.text or "Summarize the public page" in safe.text:
        add(findings, "FAIL", "safe_response_redaction", "raw query or instruction exposed")
    else:
        add(findings, "PASS", "safe_response_redaction", "query and instruction omitted")


def _dry_run_negative_checks(findings, admin_client, viewer, agent_id):
    viewer_client = make_client(viewer)
    viewer_resp = viewer_client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={"instruction": "Summarize the page", "url": "https://example.com"},
    )
    if viewer_resp.status_code == 403:
        add(findings, "PASS", "viewer_blocked", "403")
    else:
        add(findings, "FAIL", "viewer_blocked", str(viewer_resp.status_code))

    unsafe_instruction = admin_client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={"instruction": "click the submit button", "url": "https://example.com"},
    )
    if unsafe_instruction.status_code == 400:
        add(findings, "PASS", "unsafe_instruction_blocked", "400")
    else:
        add(findings, "FAIL", "unsafe_instruction_blocked", str(unsafe_instruction.status_code))

    unsafe_url = admin_client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={"instruction": "Summarize the page", "url": "javascript:alert(1)"},
    )
    if unsafe_url.status_code == 400:
        add(findings, "PASS", "unsafe_url_blocked", "400")
    else:
        add(findings, "FAIL", "unsafe_url_blocked", str(unsafe_url.status_code))


def _dry_run_audit_redaction(findings, _al):
    log_text = _al._LOG_PATH.read_text(encoding="utf-8") if _al._LOG_PATH.exists() else ""
    if "private=query" in log_text or "Summarize the public page" in log_text:
        add(findings, "FAIL", "audit_redaction", "raw query or instruction logged")
    else:
        add(findings, "PASS", "audit_redaction", "no raw query or instruction")


def dry_run() -> DryRunResult:
    findings: list[Finding] = []

    status_lines = git_status_short()
    staged_oos = sorted(staged_paths(status_lines) & OUT_OF_SCOPE)
    if staged_oos:
        add(findings, "FAIL", "out_of_scope_staged", ", ".join(staged_oos))
    else:
        add(findings, "PASS", "out_of_scope_staged", "none")

    from ai_orchestrator.agent_hub.registry import common as _reg_common
    from ai_orchestrator.agent_hub.registry import facade as _reg
    from ai_orchestrator.audit import audit_logger as _al
    from tools.gates import approval as _ap

    DRY_RUN_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    _al._LOG_PATH = DRY_RUN_TMP_ROOT / f"audit_{run_id}.jsonl"
    _ap._STORE_PATH = DRY_RUN_TMP_ROOT / f"approval_tokens_{run_id}.jsonl"
    # _reg.clear() 는 data/local_agent_registry_state.json(실제로 등록된 로컬 에이전트
    # 상태)도 unlink 한다(2026-09-30 conftest.py 의 같은 격리 패턴 참고) — pytest 밖에서
    # 단독 스크립트로 돌리면 그 autouse fixture 가 안 걸려 실제 상태 파일이 지워졌다
    # (2026-10-10 브라우저 승인 스모크 사전조사 중 발견). 임시 경로로 바꿔치기.
    _reg_common._REGISTRY_STATE_PATH = DRY_RUN_TMP_ROOT / f"local_agent_registry_state_{run_id}.json"
    try:
        _reg.clear()
        _ap._store.clear()
        _ap.clear_rate_store()

        admin = {"actor": "dry_run_admin", "role": "admin"}
        viewer = {"actor": "dry_run_viewer", "role": "viewer"}
        admin_client = make_client(admin)
        agent_id = register_agent(admin_client)

        _dry_run_admin_checks(findings, admin_client, agent_id)

        _dry_run_negative_checks(findings, admin_client, viewer, agent_id)

        _dry_run_audit_redaction(findings, _al)

        _reg.clear()
        _ap._store.clear()
        _ap.clear_rate_store()
    finally:
        _reg.clear()
        _ap._store.clear()
        _ap.clear_rate_store()

    rendered = "\n".join(f"{f.status} {f.item} {f.detail}" for f in findings)
    if any(pattern.search(rendered) for pattern in SENSITIVE_PATTERNS):
        add(findings, "FAIL", "dry_run_secret_output", "secret-shaped output detected")
    else:
        add(findings, "PASS", "dry_run_secret_output", "no secret-shaped output")

    fail_count = sum(1 for finding in findings if finding.status == "FAIL")
    if staged_oos:
        verdict = "FAIL_OUT_OF_SCOPE_MUTATED"
    elif fail_count:
        verdict = "FAIL_APPROVED_BROWSER_INSTRUCTION_API_DRY_RUN"
    else:
        verdict = "PASS_APPROVED_BROWSER_INSTRUCTION_API_DRY_RUN_READY"
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
