from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from local_agent.network_bypass import direct_child_env, urlopen_for_server


ROOT = Path(__file__).resolve().parent
DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"


def _mask_agent_id(agent_id: str) -> str:
    if not agent_id:
        return "-"
    return f"{agent_id[:6]}***{agent_id[-4:]}" if len(agent_id) > 10 else agent_id[:3] + "***"


def _load_agent_id() -> str:
    from local_agent import desktop_config

    return desktop_config.load_config().agent_id.strip()


def _basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _request_json(method: str, url: str, body: dict | None = None,
                  basic_auth: tuple[str, str] | None = None,
                  timeout: int = 10) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if basic_auth is not None:
        headers["Authorization"] = _basic_header(*basic_auth)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urlopen_for_server(url, req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        return resp.status, payload


def _start_worker(server_url: str, log_path: Path) -> subprocess.Popen:
    env = direct_child_env()
    env["HAEHAN_AGENT_WS_ENABLED"] = "true"
    env["HAEHAN_AGENT_POLL_SEC"] = "2"
    env["PYTHONIOENCODING"] = "utf-8"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out = open(log_path, "a", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "local_agent.agent",
            "--run",
            "--server",
            server_url,
        ],
        cwd=ROOT,
        env=env,
        stdout=out,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _stop_worker(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout", type=int, default=70)
    parser.add_argument("--user", default=os.getenv("HAEHAN_AGENT_USER", ""))
    parser.add_argument("--password", default=os.getenv("HAEHAN_AGENT_PASSWORD", ""))
    parser.add_argument(
        "--temp-admin",
        action="store_true",
        help="create a short-lived remote admin user for authenticated live verification",
    )
    args = parser.parse_args(argv)

    server_url = args.server.rstrip("/")
    agent_id = _load_agent_id()
    if not agent_id:
        print("[FAIL] agent config - agent_id missing")
        print("RESULT=FAIL_LIVE_TASK_DISPATCH")
        return 1

    auth: tuple[str, str] | None = None
    temp_admin_user = ""
    if args.user:
        auth = (args.user, args.password)
    elif args.temp_admin:
        from scripts.ops.live_approved_browser_instruction_smoke import remote_user

        temp_admin_user = f"codex_dispatch_{secrets.token_hex(4)}"
        temp_admin_password = secrets.token_urlsafe(24)
        remote_user("add", temp_admin_user, temp_admin_password)
        auth = (temp_admin_user, temp_admin_password)
        print("[PASS] temp admin user added")

    log_path = ROOT / "logs" / "live_task_worker.log"
    worker = _start_worker(server_url, log_path)
    print(f"[PASS] worker start - pid={worker.pid} agent_id={_mask_agent_id(agent_id)}")

    try:
        time.sleep(5)
        if worker.poll() is not None:
            print(f"[FAIL] worker exited early - code={worker.returncode}")
            print("RESULT=FAIL_LIVE_TASK_DISPATCH")
            return 1

        tasks_url = f"{server_url}/api/v1/local-agents/{agent_id}/tasks"
        try:
            status, created = _request_json(
                "POST",
                tasks_url,
                {"action": "ws_noop", "params": {}},
                basic_auth=auth,
            )
        except urllib.error.HTTPError as exc:
            print(f"[FAIL] task create - status={exc.code}")
            print("RESULT=FAIL_LIVE_TASK_DISPATCH")
            return 1
        except (urllib.error.URLError, OSError) as exc:
            print(f"[FAIL] task create - {type(exc).__name__}")
            print("RESULT=FAIL_LIVE_TASK_DISPATCH")
            return 1

        task_id = str(created.get("task_id") or "")
        initial_status = str(created.get("status") or "")
        if status != 200 or not task_id:
            print(f"[FAIL] task create - status={status} task_id_present={bool(task_id)}")
            print("RESULT=FAIL_LIVE_TASK_DISPATCH")
            return 1
        print(f"[PASS] task create - task_id={task_id} status={initial_status}")

        detail_url = f"{tasks_url}/{task_id}"
        deadline = time.time() + args.timeout
        last_status = initial_status
        last_error = ""
        while time.time() < deadline:
            time.sleep(2)
            try:
                _, detail = _request_json("GET", detail_url, basic_auth=auth)
            except Exception as exc:
                last_error = type(exc).__name__
                continue
            last_status = str(detail.get("status") or last_status)
            last_error = str(detail.get("error_code") or "")
            if last_status in {"completed", "failed", "cancelled", "expired"}:
                break

        print(f"[PASS] task final observed - task_id={task_id} status={last_status}")
        if last_status == "completed":
            print("RESULT=PASS_LIVE_TASK_DISPATCH")
            return 0
        print(f"[FAIL] task not completed - status={last_status} error_code={last_error or '-'}")
        print("RESULT=FAIL_LIVE_TASK_DISPATCH")
        return 1
    finally:
        _stop_worker(worker)
        print("[PASS] worker stopped")
        if temp_admin_user:
            try:
                from scripts.ops.live_approved_browser_instruction_smoke import remote_user

                remote_user("remove", temp_admin_user)
                print("[PASS] temp admin user removed")
            except Exception:
                print("[WARN] temp admin user cleanup failed")


if __name__ == "__main__":
    raise SystemExit(main())
