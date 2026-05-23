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
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from local_agent.network_bypass import direct_child_env, urlopen_for_server

DEFAULT_SERVER = "https://haehan-ai.kr/orchestrator"
REMOTE_HOST = "haehan-app"

REMOTE_USER_SCRIPT = r"""
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
path = Path("/home/ubuntu/apps/haehan-ai-orchestrator-api/secrets/api/http_users.json")
raw = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(raw, list):
    raise SystemExit("http_users format is not a list")

username = payload["username"]
action = payload["action"]
raw = [rec for rec in raw if not (isinstance(rec, dict) and rec.get("username") == username)]

if action == "add":
    password = payload["password"]
    salt = secrets.token_bytes(16)
    digest = hashlib.sha256(salt + password.encode("utf-8")).hexdigest()
    raw.append({
        "username": username,
        "password_hash": f"sha256${salt.hex()}${digest}",
        "role": "admin",
        "enabled": True,
    })
elif action != "remove":
    raise SystemExit("unknown action")

tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
os.chmod(path, 0o600)
print("OK")
"""


WORKER_CODE = r"""
import os
from local_agent import config
from local_agent import websocket_client

config.SERVER_BASE_URL = os.environ["HAEHAN_LIVE_SERVER_URL"]
config.WEBSOCKET_ENABLED = True
websocket_client.connect(
    os.environ["HAEHAN_LIVE_AGENT_ID"],
    os.environ["HAEHAN_LIVE_DEVICE_TOKEN"],
)
"""


def mask_agent_id(agent_id: str) -> str:
    return f"{agent_id[:6]}***{agent_id[-4:]}" if len(agent_id) > 10 else "***"


def basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
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


def remote_user(action: str, username: str, password: str = "") -> None:
    payload = {"action": action, "username": username, "password": password}
    encoded = base64.b64encode(REMOTE_USER_SCRIPT.encode("utf-8")).decode("ascii")
    remote_command = f"python3 -c 'import base64; exec(base64.b64decode(\"{encoded}\"))'"
    proc = subprocess.run(
        ["ssh", REMOTE_HOST, remote_command],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        safe_detail = detail[-1][:200] if detail else "no remote detail"
        raise RuntimeError(f"remote user {action} failed: rc={proc.returncode} detail={safe_detail}")


def start_worker(server_url: str, agent_id: str, device_token: str) -> subprocess.Popen:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    env = direct_child_env()
    env["HAEHAN_LIVE_SERVER_URL"] = server_url
    env["HAEHAN_LIVE_AGENT_ID"] = agent_id
    env["HAEHAN_LIVE_DEVICE_TOKEN"] = device_token
    env["HAEHAN_AGENT_AUDIT"] = str(logs / "live_approved_browser_instruction_audit.jsonl")
    env["PYTHONIOENCODING"] = "utf-8"
    log = open(logs / "live_approved_browser_instruction_worker.log", "a", encoding="utf-8")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--url", default="https://example.com/")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--keep-open-ms", type=int, default=0)
    args = parser.parse_args(argv)

    server = args.server.rstrip("/")
    username = f"codex_browser_smoke_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    worker: subprocess.Popen | None = None

    try:
        remote_user("add", username, password)
        print("[PASS] temp admin user added")

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

        auth = (username, password)
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
            return 1
        print("[PASS] registration code issued - redacted")

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
        time.sleep(6)
        if worker.poll() is not None:
            print(f"[FAIL] local worker exited early - code={worker.returncode}")
            print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
            return 1

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
            },
        )
        task_id = str(queued.get("task_id") or "")
        if not task_id:
            print("[FAIL] browser instruction task id missing")
            print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
            return 1
        if "Summarize the public page" in json.dumps(queued) or "?" in str(queued.get("url_host", "")):
            print("[FAIL] browser instruction response leaked raw input")
            print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
            return 1
        print(f"[PASS] browser instruction queued - task_id={task_id}")

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
            except Exception:
                continue
            last_status = str(detail.get("status") or last_status)
            if last_status in {"completed", "failed", "cancelled", "expired"}:
                break

        print(f"[PASS] task final observed - status={last_status}")
        if last_status != "completed":
            print("RESULT=FAIL_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
            return 1

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
                f"keep_open_ms={observe.get('browser_keep_open_ms')}"
            )
        else:
            print("[WARN] observe summary - not returned")
        print("RESULT=PASS_APPROVED_BROWSER_INSTRUCTION_LIVE_SMOKE")
        return 0
    finally:
        stop_worker(worker)
        try:
            remote_user("remove", username)
            print("[PASS] temp admin user removed")
        except Exception:
            print("[WARN] temp admin user cleanup failed")


if __name__ == "__main__":
    raise SystemExit(main())
