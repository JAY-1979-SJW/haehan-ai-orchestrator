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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 루트 패키지(local_agent 등) 해석용
from core.agent_runtime.connection.network_bypass import direct_child_env, urlopen_for_server
from scripts.common.app_paths import repo_root

ROOT = repo_root()
DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"


def _mask_agent_id(agent_id: str) -> str:
    if not agent_id:
        return "-"
    return f"{agent_id[:6]}***{agent_id[-4:]}" if len(agent_id) > 10 else agent_id[:3] + "***"


def _load_agent_id() -> str:
    from core.agent_runtime.common import desktop_config

    return desktop_config.load_config().agent_id.strip()


def _register_temp_agent(
    *,
    server_url: str,
    auth: tuple[str, str],
) -> tuple[str, str]:
    _, issued = _request_json(
        "POST",
        f"{server_url}/api/v1/local-agents/registration-codes",
        {
            "label": "codex-live-task-dispatch-smoke",
            "expires_in_minutes": 10,
            "allowed_actions": ["ws_noop"],
            "note": "live task dispatch smoke",
            "smoke_test": True,
        },
        basic_auth=auth,
        timeout=15,
    )
    registration_code = str(issued.get("registration_code") or "")
    if not registration_code:
        raise RuntimeError("registration code missing")

    _, registered = _request_json(
        "POST",
        f"{server_url}/api/v1/local-agents/register-with-code",
        {
            "registration_code": registration_code,
            "host": "codex-live-task-local",
            "os_name": "Windows",
            "version": "task-dispatch-smoke",
        },
        timeout=15,
    )
    agent_id = str(registered.get("agent_id") or "")
    device_token = str(registered.get("device_token") or "")
    if not agent_id or not device_token:
        raise RuntimeError("agent registration missing credentials")
    return agent_id, device_token


def _basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def _request_json(
    method: str, url: str, body: dict | None = None, basic_auth: tuple[str, str] | None = None, timeout: int = 10
) -> tuple[int, dict]:
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
    out = log_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "core.agent_runtime.agent",
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


def _start_token_worker(
    server_url: str,
    agent_id: str,
    device_token: str,
    log_path: Path,
) -> subprocess.Popen:
    from tools.verify._shared import WORKER_CODE

    env = direct_child_env()
    env["HAEHAN_LIVE_SERVER_URL"] = server_url
    env["HAEHAN_LIVE_AGENT_ID"] = agent_id
    env["HAEHAN_LIVE_DEVICE_TOKEN"] = device_token
    env["HAEHAN_AGENT_AUDIT"] = str(ROOT / "logs" / "live_task_dispatch_audit.jsonl")
    env["PYTHONIOENCODING"] = "utf-8"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out = log_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-c", WORKER_CODE],
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


def _resolve_identity(args, server_url):
    agent_id = ""
    device_token = ""

    auth: tuple[str, str] | None = None
    temp_admin_user = ""
    if args.user:
        auth = (args.user, args.password)
    elif args.temp_admin:
        from tools.verify._shared import remote_user

        temp_admin_user = f"codex_dispatch_{secrets.token_hex(4)}"
        temp_admin_password = secrets.token_urlsafe(24)
        remote_user("add", temp_admin_user, temp_admin_password)
        auth = (temp_admin_user, temp_admin_password)
        print("[PASS] temp admin user added")
        try:
            agent_id, device_token = _register_temp_agent(server_url=server_url, auth=auth)
        except Exception as exc:  # noqa: BLE001 - 라이브 태스크 디스패치 검증 스크립트 -- 임시 에이전트 등록 실패 시 FAIL 처리 후 종료(fail-closed), 상태 폴링 조회 실패는 다음 루프에서 재시도, 임시 관리자 계정 정리 실패는 경고만 출력(검증 결과를 바꾸지 않음)
            print(f"[FAIL] temp agent register - {type(exc).__name__}")
            print("RESULT=FAIL_LIVE_TASK_DISPATCH")
            return (1), None, None, None, None
        print(f"[PASS] temp agent registered - agent_id={_mask_agent_id(agent_id)}")
    else:
        agent_id = _load_agent_id()
        if not agent_id:
            print("[FAIL] agent config - agent_id missing")
            print("RESULT=FAIL_LIVE_TASK_DISPATCH")
            return (1), None, None, None, None
    return None, auth, temp_admin_user, agent_id, device_token


def _check_worker_alive(worker):
    time.sleep(5)
    if worker.poll() is not None:
        print(f"[FAIL] worker exited early - code={worker.returncode}")
        print("RESULT=FAIL_LIVE_TASK_DISPATCH")
        return 1
    return None


def _create_task(tasks_url, auth):
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
        return (1), None, None, None
    except (urllib.error.URLError, OSError) as exc:
        print(f"[FAIL] task create - {type(exc).__name__}")
        print("RESULT=FAIL_LIVE_TASK_DISPATCH")
        return (1), None, None, None

    task_id = str(created.get("task_id") or "")
    initial_status = str(created.get("status") or "")
    if status != 200 or not task_id:
        print(f"[FAIL] task create - status={status} task_id_present={bool(task_id)}")
        print("RESULT=FAIL_LIVE_TASK_DISPATCH")
        return (1), None, None, None
    print(f"[PASS] task create - task_id={task_id} status={initial_status}")
    return None, created, task_id, initial_status


def _poll_and_report(tasks_url, task_id, initial_status, auth, args):
    detail_url = f"{tasks_url}/{task_id}"
    deadline = time.time() + args.timeout
    last_status = initial_status
    last_error = ""
    while time.time() < deadline:
        time.sleep(2)
        try:
            _, detail = _request_json("GET", detail_url, basic_auth=auth)
        except Exception as exc:  # noqa: BLE001 - 라이브 태스크 디스패치 검증 스크립트 -- 임시 에이전트 등록 실패 시 FAIL 처리 후 종료(fail-closed), 상태 폴링 조회 실패는 다음 루프에서 재시도, 임시 관리자 계정 정리 실패는 경고만 출력(검증 결과를 바꾸지 않음)
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
    return None


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
    _early, auth, temp_admin_user, agent_id, device_token = _resolve_identity(args, server_url)
    if _early is not None:
        return _early

    log_path = ROOT / "logs" / "live_task_worker.log"
    worker = (
        _start_token_worker(server_url, agent_id, device_token, log_path)
        if device_token
        else _start_worker(server_url, log_path)
    )
    device_token = ""
    print(f"[PASS] worker start - pid={worker.pid} agent_id={_mask_agent_id(agent_id)}")

    try:
        _early = _check_worker_alive(worker)
        if _early is not None:
            return _early

        tasks_url = f"{server_url}/api/v1/local-agents/{agent_id}/tasks"
        _early, _created, task_id, initial_status = _create_task(tasks_url, auth)
        if _early is not None:
            return _early

        _early = _poll_and_report(tasks_url, task_id, initial_status, auth, args)
        if _early is not None:
            return _early
    finally:
        _stop_worker(worker)
        print("[PASS] worker stopped")
        if temp_admin_user:
            try:
                from tools.verify._shared import remote_user

                remote_user("remove", temp_admin_user)
                print("[PASS] temp admin user removed")
            except Exception:  # noqa: BLE001 - 라이브 태스크 디스패치 검증 스크립트 -- 임시 에이전트 등록 실패 시 FAIL 처리 후 종료(fail-closed), 상태 폴링 조회 실패는 다음 루프에서 재시도, 임시 관리자 계정 정리 실패는 경고만 출력(검증 결과를 바꾸지 않음)
                print("[WARN] temp admin user cleanup failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
