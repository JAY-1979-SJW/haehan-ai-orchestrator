"""Live smoke for approved-user readonly browser instruction dispatch.

Flow:
1. Add a temporary admin user on the remote server without printing secrets.
2. Issue a one-time local-agent registration code through the live API.
3. Register a temporary local agent and connect it over WebSocket.
4. Queue a readonly browser instruction through the new high-level API.
5. Wait for the local Playwright result and remove the temporary admin user.

This script intentionally never prints passwords, registration codes, device
tokens, or Authorization header values.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))

from core.agent_runtime.connection.network_bypass import (  # noqa: E402
    direct_child_env,
    urlopen_for_server,
)

DEFAULT_SERVER = "https://haehan-ai.kr/orchestrator"
from tools.verify._shared import (  # noqa: E402, F401  (verify 공유 모듈에서 재노출)
    REMOTE_HOST,
    REMOTE_USER_SCRIPT,
    WORKER_CODE,
    remote_user,
)


def mask_agent_id(agent_id: str) -> str:
    return f"{agent_id[:6]}***{agent_id[-4:]}" if len(agent_id) > 10 else "***"


def basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def request_json(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    auth: tuple[str, str] | None = None,
    timeout: int = 15,
) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if auth is not None:
        headers["Authorization"] = basic_header(*auth)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urlopen_for_server(url, req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, json.loads(raw) if raw else {}


def start_worker(server_url: str, agent_id: str, device_token: str) -> subprocess.Popen:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    env = direct_child_env()
    env["HAEHAN_LIVE_SERVER_URL"] = server_url
    env["HAEHAN_LIVE_AGENT_ID"] = agent_id
    env["HAEHAN_LIVE_DEVICE_TOKEN"] = device_token
    env["HAEHAN_AGENT_AUDIT"] = str(logs / "live_approved_browser_instruction_audit.jsonl")
    env["PYTHONIOENCODING"] = "utf-8"
    log = (logs / "live_approved_browser_instruction_worker.log").open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-c", WORKER_CODE],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def stop_worker(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


def _check_unauth_blocked(server):
    try:
        request_json("GET", f"{server}/api/v1/local-agents/registration-codes", timeout=10)
        print("[FAIL] unauth registration-code list unexpectedly allowed")
        print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return 1
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("[PASS] unauth admin endpoint blocked - 401")
        else:
            print(f"[FAIL] unauth admin endpoint unexpected status - {exc.code}")
            print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
            return 1
    return None


def _issue_registration_code(server, auth):
    _, issued = request_json(
        "POST",
        f"{server}/api/v1/local-agents/registration-codes",
        auth=auth,
        body={
            "label": "codex-live-browser-smoke",
            "expires_in_minutes": 10,
            "allowed_actions": ["web_open_url_readonly"],
            "note": "live readonly browser smoke",
            "smoke_test": True,
        },
    )
    registration_code = str(issued.get("registration_code") or "")
    if not registration_code:
        print("[FAIL] registration code missing")
        print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return (1), None
    print("[PASS] registration code issued - redacted")
    return None, registration_code


def _register_with_code(server, registration_code):
    _, registered = request_json(
        "POST",
        f"{server}/api/v1/local-agents/register-with-code",
        body={
            "registration_code": registration_code,
            "host": "codex-live-local",
            "os_name": "Windows",
            "version": "live-smoke",
        },
    )
    return registered


def _check_worker_alive(worker):
    time.sleep(6)
    if worker.poll() is not None:
        print(f"[FAIL] local worker exited early - code={worker.returncode}")
        print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return 1
    return None


def _queue_instruction(server, agent_id, auth, args):
    _, queued = request_json(
        "POST",
        f"{server}/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        auth=auth,
        body={
            "instruction": "Summarize the public page title and link count only",
            "url": args.url,
            "wait_until": "domcontentloaded",
            "timeout_ms": 20000,
            "max_html_chars": 100000,
            "visible_browser": bool(args.visible),
            "keep_open_ms": max(0, min(int(args.keep_open_ms), 30000)),
            "browser_channel": args.browser_channel,
        },
    )
    task_id = str(queued.get("task_id") or "")
    if not task_id:
        print("[FAIL] browser instruction task id missing")
        print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return (1), None, None
    if "Summarize the public page" in json.dumps(queued) or "?" in str(queued.get("url_host", "")):
        print("[FAIL] browser instruction response leaked raw input")
        print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return (1), None, None
    print(f"[PASS] browser instruction queued - task_id={task_id}")
    return None, queued, task_id


def _poll_task(server, agent_id, task_id, auth, queued, args):
    deadline = time.time() + args.timeout
    detail = queued
    last_status = str(queued.get("status") or "")
    while time.time() < deadline:
        time.sleep(2)
        try:
            _, detail = request_json(
                "GET",
                f"{server}/api/v1/local-agents/{agent_id}/tasks/{task_id}",
                auth=auth,
                timeout=10,
            )
        except Exception:  # noqa: BLE001 - 스모크테스트 진행상태 폴링 중 일시적 HTTP 조회 실패는 재시도 루프에서 continue, 테스트용 임시 관리자 계정(codex_browser_smoke_*) 정리 실패는 WARN 출력만(운영 계정이 아닌 테스트 전용 임시계정)
            continue
        last_status = str(detail.get("status") or last_status)
        if last_status in {"completed", "failed", "cancelled", "expired"}:
            break

    print(f"[PASS] task final observed - status={last_status}")
    if last_status != "completed":
        print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return (1), None
    return None, detail


def _report_result(detail):
    summary = str(detail.get("result_summary") or "")[:240]
    observe = detail.get("observe_summary") if isinstance(detail.get("observe_summary"), dict) else {}
    print(f"[PASS] result summary - {summary}")
    if observe:
        print(
            "[PASS] observe summary - "
            f"status={observe.get('status_category')} "
            f"title_len={observe.get('title_len')} "
            f"pages={observe.get('pages_observed_count')} "
            f"headless={observe.get('browser_headless')} "
            f"keep_open_ms={observe.get('browser_keep_open_ms')} "
            f"channel={observe.get('browser_channel')}"
        )
    else:
        print("[WARN] observe summary - not returned")
    print("RESULT=PASS_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
    return 0
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--url", default="https://example.com/")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--keep-open-ms", type=int, default=0)
    parser.add_argument("--browser-channel", default="chromium", choices=("chromium", "chrome", "msedge"))
    args = parser.parse_args(argv)

    server = args.server.rstrip("/")
    username = f"codex_browser_smoke_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    worker: subprocess.Popen | None = None

    try:
        remote_user("add", username, password)
        print("[PASS] temp admin user added")

        _early = _check_unauth_blocked(server)
        if _early is not None:
            return _early

        auth = (username, password)
        _early, registration_code = _issue_registration_code(server, auth)
        if _early is not None:
            return _early

        registered = _register_with_code(server, registration_code)
        registration_code = ""
        agent_id = str(registered.get("agent_id") or "")
        device_token = str(registered.get("device_token") or "")
        if not agent_id or not device_token:
            print("[FAIL] agent registration missing credentials")
            print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
            return 1
        print(f"[PASS] temp agent registered - agent_id={mask_agent_id(agent_id)}")

        worker = start_worker(server, agent_id, device_token)
        device_token = ""
        print(f"[PASS] local worker started - pid={worker.pid}")
        _early = _check_worker_alive(worker)
        if _early is not None:
            return _early

        _early, queued, task_id = _queue_instruction(server, agent_id, auth, args)
        if _early is not None:
            return _early

        _early, detail = _poll_task(server, agent_id, task_id, auth, queued, args)
        if _early is not None:
            return _early

        _early = _report_result(detail)
        if _early is not None:
            return _early
    finally:
        stop_worker(worker)
        try:
            remote_user("remove", username)
            print("[PASS] temp admin user removed")
        except Exception:  # noqa: BLE001 - 스모크테스트 진행상태 폴링 중 일시적 HTTP 조회 실패는 재시도 루프에서 continue, 테스트용 임시 관리자 계정(codex_browser_smoke_*) 정리 실패는 WARN 출력만(운영 계정이 아닌 테스트 전용 임시계정)
            print("[WARN] temp admin user cleanup failed")


if __name__ == "__main__":
    raise SystemExit(main())
