"""Live smoke for parallel server task submission to one local agent.

This check verifies the server-first path:

server concurrent task creation -> local-agent WebSocket dispatch
-> local ws_noop execution -> server task result state.

It does not prove parallel local execution inside one local agent process. The
current local agent processes one WebSocket task at a time; this smoke verifies
that concurrent submissions are safely queued and all complete without loss.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_runtime.connection.network_bypass import direct_child_env, urlopen_for_server  # noqa: E402

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
            "label": "codex-live-parallel-smoke",
            "expires_in_minutes": 10,
            "allowed_actions": ["ws_noop"],
            "note": "live parallel task dispatch smoke",
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
            "host": "codex-live-parallel-local",
            "os_name": "Windows",
            "version": "parallel-smoke",
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
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    basic_auth: tuple[str, str] | None = None,
    timeout: int = 10,
) -> tuple[int, dict[str, Any]]:
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
    from tools.smoke.live_approved_browser_instruction_smoke import WORKER_CODE

    env = direct_child_env()
    env["HAEHAN_LIVE_SERVER_URL"] = server_url
    env["HAEHAN_LIVE_AGENT_ID"] = agent_id
    env["HAEHAN_LIVE_DEVICE_TOKEN"] = device_token
    env["HAEHAN_AGENT_AUDIT"] = str(ROOT / "logs" / "live_parallel_task_audit.jsonl")
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


def _create_task(
    *,
    tasks_url: str,
    auth: tuple[str, str] | None,
    index: int,
) -> dict[str, Any]:
    status, payload = _request_json(
        "POST",
        tasks_url,
        {
            "action": "ws_noop",
            "params": {
                "parallel_smoke": True,
                "index": index,
            },
        },
        basic_auth=auth,
        timeout=15,
    )
    return {
        "index": index,
        "http_status": status,
        "task_id": str(payload.get("task_id") or ""),
        "initial_status": str(payload.get("status") or ""),
    }


def _poll_task(
    *,
    detail_url: str,
    auth: tuple[str, str] | None,
) -> tuple[str, str]:
    _, detail = _request_json("GET", detail_url, basic_auth=auth, timeout=10)
    return str(detail.get("status") or ""), str(detail.get("error_code") or "")


def _resolve_identity(args, server_url):
    agent_id = ""
    device_token = ""

    auth: tuple[str, str] | None = None
    temp_admin_user = ""
    if args.user:
        auth = (args.user, args.password)
    elif args.temp_admin:
        from tools.smoke.live_approved_browser_instruction_smoke import remote_user

        temp_admin_user = f"codex_parallel_{secrets.token_hex(4)}"
        temp_admin_password = secrets.token_urlsafe(24)
        remote_user("add", temp_admin_user, temp_admin_password)
        auth = (temp_admin_user, temp_admin_password)
        print("[PASS] temp admin user added")
        try:
            agent_id, device_token = _register_temp_agent(server_url=server_url, auth=auth)
        except Exception as exc:  # noqa: BLE001 - 병렬 작업 디스패치 스모크테스트(임시 계정/에이전트 생성 후 자체 정리) — 임시 에이전트 등록 실패는 FAIL 결과 반환, 상태폴링 실패는 continue로 다음 폴링, 임시 관리자계정 정리(remove) 실패는 경고만 출력 — 모두 테스트용 임시 리소스이며 운영 데이터 아님
            print(f"[FAIL] temp agent register - {type(exc).__name__}")
            print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
            return (1), None, None, None, None
        print(f"[PASS] temp agent registered - agent_id={_mask_agent_id(agent_id)}")
    else:
        agent_id = _load_agent_id()
        if not agent_id:
            print("[FAIL] agent config - agent_id missing")
            print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
            return (1), None, None, None, None
    return None, auth, temp_admin_user, agent_id, device_token


def _check_worker_alive(worker):
    time.sleep(5)
    if worker.poll() is not None:
        print(f"[FAIL] worker exited early - code={worker.returncode}")
        print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
        return 1
    return None


def _create_tasks_parallel(tasks_url, auth, count, concurrency):
    started_at = time.time()
    created: list[dict[str, Any]] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(
                    _create_task,
                    tasks_url=tasks_url,
                    auth=auth,
                    index=i,
                )
                for i in range(count)
            ]
            for future in concurrent.futures.as_completed(futures):
                created.append(future.result())
    except urllib.error.HTTPError as exc:
        print(f"[FAIL] task create - status={exc.code}")
        print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
        return (1), None, None
    except (urllib.error.URLError, OSError) as exc:
        print(f"[FAIL] task create - {type(exc).__name__}")
        print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
        return (1), None, None
    return None, created, started_at


def _report_created(created, count, concurrency, started_at):
    created.sort(key=lambda row: int(row["index"]))
    creation_elapsed_ms = int((time.time() - started_at) * 1000)
    task_ids = [row["task_id"] for row in created if row["task_id"]]
    all_created = len(task_ids) == count and all(row["http_status"] == 200 for row in created)
    print(
        "[PASS]" if all_created else "[FAIL]",
        "parallel task create - "
        f"count={len(task_ids)}/{count} concurrency={concurrency} elapsed_ms={creation_elapsed_ms}",
    )
    for row in created:
        print(
            "  task "
            f"index={row['index']} id={row['task_id'] or '-'} "
            f"initial={row['initial_status'] or '-'} http={row['http_status']}"
        )
    if not all_created:
        print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
        return (1), None
    return None, task_ids


def _poll_all(task_ids, tasks_url, auth, args):
    pending = set(task_ids)
    final: dict[str, tuple[str, str]] = {}
    deadline = time.time() + args.timeout
    while pending and time.time() < deadline:
        time.sleep(2)
        for task_id in list(pending):
            try:
                status, error_code = _poll_task(
                    detail_url=f"{tasks_url}/{task_id}",
                    auth=auth,
                )
            except Exception:  # noqa: BLE001 - 병렬 작업 디스패치 스모크테스트(임시 계정/에이전트 생성 후 자체 정리) — 임시 에이전트 등록 실패는 FAIL 결과 반환, 상태폴링 실패는 continue로 다음 폴링, 임시 관리자계정 정리(remove) 실패는 경고만 출력 — 모두 테스트용 임시 리소스이며 운영 데이터 아님
                continue
            if status in {"completed", "failed", "cancelled", "expired"}:
                final[task_id] = (status, error_code)
                pending.remove(task_id)
    return pending, final


def _report_final(pending, final, count):
    completed = [task_id for task_id, (status, _) in final.items() if status == "completed"]
    failed = {
        task_id: {"status": status, "error_code": error_code}
        for task_id, (status, error_code) in final.items()
        if status != "completed"
    }
    for task_id in sorted(pending):
        failed[task_id] = {"status": "timeout", "error_code": ""}

    print(
        "[PASS]" if len(completed) == count else "[FAIL]",
        f"parallel task final - completed={len(completed)}/{count} failed={len(failed)}",
    )
    if failed:
        print(json.dumps(failed, ensure_ascii=False, indent=2))
        print("RESULT=FAIL_LIVE_PARALLEL_TASK_DISPATCH")
        return 1

    print("[PASS] server queued concurrent submissions; single local agent completed all ws_noop tasks")
    print("[WARN] local execution model - single worker processes tasks sequentially per agent")
    print("RESULT=PASS_LIVE_PARALLEL_TASK_DISPATCH")
    return 0
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--user", default=os.getenv("HAEHAN_AGENT_USER", ""))
    parser.add_argument("--password", default=os.getenv("HAEHAN_AGENT_PASSWORD", ""))
    parser.add_argument(
        "--temp-admin",
        action="store_true",
        help="create a short-lived remote admin user for authenticated live verification",
    )
    args = parser.parse_args(argv)

    count = max(2, min(args.count, 20))
    concurrency = max(2, min(args.concurrency, count))
    server_url = args.server.rstrip("/")
    _early, auth, temp_admin_user, agent_id, device_token = _resolve_identity(args, server_url)
    if _early is not None:
        return _early

    log_path = ROOT / "logs" / "live_parallel_task_worker.log"
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
        _early, created, started_at = _create_tasks_parallel(tasks_url, auth, count, concurrency)
        if _early is not None:
            return _early

        _early, task_ids = _report_created(created, count, concurrency, started_at)
        if _early is not None:
            return _early

        pending, final = _poll_all(task_ids, tasks_url, auth, args)

        _early = _report_final(pending, final, count)
        if _early is not None:
            return _early
    finally:
        _stop_worker(worker)
        print("[PASS] worker stopped")
        if temp_admin_user:
            try:
                from tools.smoke.live_approved_browser_instruction_smoke import remote_user

                remote_user("remove", temp_admin_user)
                print("[PASS] temp admin user removed")
            except Exception:  # noqa: BLE001 - 병렬 작업 디스패치 스모크테스트(임시 계정/에이전트 생성 후 자체 정리) — 임시 에이전트 등록 실패는 FAIL 결과 반환, 상태폴링 실패는 continue로 다음 폴링, 임시 관리자계정 정리(remove) 실패는 경고만 출력 — 모두 테스트용 임시 리소스이며 운영 데이터 아님
                print("[WARN] temp admin user cleanup failed")


if __name__ == "__main__":
    raise SystemExit(main())
