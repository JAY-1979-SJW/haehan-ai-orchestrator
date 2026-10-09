from __future__ import annotations

import argparse
import json
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


def _request_json(method: str, url: str, body: dict | None = None, timeout: int = 10) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
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
        [sys.executable, "-m", "core.agent_runtime.agent", "--run", "--server", server_url],
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


def _create_task(tasks_url, args):
    body = {
        "action": "web_open_url_readonly",
        "params": {
            "url": args.url,
            "wait_until": "domcontentloaded",
            "timeout_ms": 20000,
            "max_html_chars": 100000,
        },
    }
    try:
        status, created = _request_json("POST", tasks_url, body)
    except urllib.error.HTTPError as exc:
        print(f"[FAIL] task create - status={exc.code}")
        print("RESULT=FAIL_LIVE_BROWSER_READONLY_DISPATCH")
        return (1), None, None, None
    except (urllib.error.URLError, OSError) as exc:
        print(f"[FAIL] task create - {type(exc).__name__}")
        print("RESULT=FAIL_LIVE_BROWSER_READONLY_DISPATCH")
        return (1), None, None, None

    task_id = str(created.get("task_id") or "")
    initial_status = str(created.get("status") or "")
    if status != 200 or not task_id:
        print(f"[FAIL] task create - status={status} task_id_present={bool(task_id)}")
        print("RESULT=FAIL_LIVE_BROWSER_READONLY_DISPATCH")
        return (1), None, None, None
    print(f"[PASS] task create - task_id={task_id} status={initial_status}")
    return None, created, task_id, initial_status


def _poll_final(tasks_url, task_id, created, initial_status, args):
    detail_url = f"{tasks_url}/{task_id}"
    deadline = time.time() + args.timeout
    detail: dict = created
    last_status = initial_status
    while time.time() < deadline:
        time.sleep(2)
        try:
            _, detail = _request_json("GET", detail_url)
        except Exception:  # noqa: BLE001 - 실행 중인 태스크 상태를 폴링하는 읽기전용 검증 스크립트 — 상태 조회(GET) 실패를 continue로 넘기고 다음 폴링에서 재시도.
            continue
        last_status = str(detail.get("status") or last_status)
        if last_status in {"completed", "failed", "cancelled", "expired"}:
            break

    print(f"[PASS] task final observed - task_id={task_id} status={last_status}")
    if last_status != "completed":
        print(f"[FAIL] task not completed - status={last_status}")
        print("RESULT=FAIL_LIVE_BROWSER_READONLY_DISPATCH")
        return (1), None
    return None, detail


def _report_result(detail):
    summary = str(detail.get("result_summary") or "")[:300]
    observe = detail.get("observe_summary") if isinstance(detail.get("observe_summary"), dict) else {}
    result_data = detail.get("result_data") if isinstance(detail.get("result_data"), dict) else {}
    print(f"[PASS] result summary - {summary}")
    if observe:
        print(
            "[PASS] observe summary - "
            f"status={observe.get('status_category')} "
            f"title_len={observe.get('title_len')} "
            f"pages={observe.get('pages_observed_count')}"
        )
    else:
        print("[WARN] observe summary - not returned by server")
    print(f"[PASS] result data stored - present={bool(result_data)}")
    print("RESULT=PASS_LIVE_BROWSER_READONLY_DISPATCH")
    return 0
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--url", default="https://example.com/")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(argv)

    server_url = args.server.rstrip("/")
    agent_id = _load_agent_id()
    if not agent_id:
        print("[FAIL] agent config - agent_id missing")
        print("RESULT=FAIL_LIVE_BROWSER_READONLY_DISPATCH")
        return 1

    log_path = ROOT / "logs" / "live_browser_readonly_worker.log"
    worker = _start_worker(server_url, log_path)
    print(f"[PASS] worker start - pid={worker.pid} agent_id={_mask_agent_id(agent_id)}")

    try:
        time.sleep(5)
        if worker.poll() is not None:
            print(f"[FAIL] worker exited early - code={worker.returncode}")
            print("RESULT=FAIL_LIVE_BROWSER_READONLY_DISPATCH")
            return 1

        tasks_url = f"{server_url}/api/v1/local-agents/{agent_id}/tasks"
        _early, created, task_id, initial_status = _create_task(tasks_url, args)
        if _early is not None:
            return _early

        _early, detail = _poll_final(tasks_url, task_id, created, initial_status, args)
        if _early is not None:
            return _early

        _early = _report_result(detail)
        if _early is not None:
            return _early
    finally:
        _stop_worker(worker)
        print("[PASS] worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
