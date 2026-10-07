"""CDP 부트스트랩 — Chrome 9222 포트 보장 기동.

흐름: probe → 미연결 시 Task Scheduler 기동 → retry probe.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request

from scripts.common.cdp_audit import L1, L2
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
TASK_NAME = "HaehanCdpChrome"
PROBE_TIMEOUT = 15
PROBE_INTERVAL = 1
ACTOR = "cdp_launcher"


def probe_cdp(host: str = CDP_HOST, port: int = CDP_PORT, timeout: float = 1.5) -> bool:
    t0 = time.time()
    url = f"http://{host}:{port}/json/version"
    ok = False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ok = r.status == 200
    except (urllib.error.URLError, ConnectionError, OSError):
        ok = False
    L1("CDP_PROBE", ACTOR, host=host, port=port, result=ok, elapsed_ms=int((time.time() - t0) * 1000))
    return ok


def is_task_registered(task_name: str = TASK_NAME) -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", task_name], capture_output=True, text=True, encoding="utf-8", timeout=5
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001 - CDP Chrome 기동 보장 유틸 — 작업스케줄러 등록여부/실행 확인 실패 시 False를 반환(등록 안 됨으로 간주해 RuntimeError로 사용자에게 안내), 탭 열기 실패는 RuntimeError로 재발생시켜 은폐되지 않음.
        return False


def start_via_scheduler(task_name: str = TASK_NAME) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["schtasks", "/run", "/tn", task_name], capture_output=True, text=True, encoding="utf-8", timeout=10
        )
        ok = r.returncode == 0
        msg = ((r.stdout or "") + (r.stderr or "")).strip()
        L2("CDP_TASK_TRIGGER", ACTOR, task_name=task_name, exit_code=r.returncode)
        return ok, msg
    except Exception as e:  # noqa: BLE001 - CDP Chrome 기동 보장 유틸 — 작업스케줄러 등록여부/실행 확인 실패 시 False를 반환(등록 안 됨으로 간주해 RuntimeError로 사용자에게 안내), 탭 열기 실패는 RuntimeError로 재발생시켜 은폐되지 않음.
        L2("CDP_TASK_TRIGGER", ACTOR, task_name=task_name, exit_code=-1, error=str(e))
        return False, str(e)


def ensure_cdp(
    host: str = CDP_HOST, port: int = CDP_PORT, task_name: str = TASK_NAME, timeout: float = PROBE_TIMEOUT
) -> str:
    t0 = time.time()
    base = f"http://{host}:{port}"

    if probe_cdp(host, port):
        L2("CDP_BOOT_OK", ACTOR, host=host, port=port, retries=0, total_ms=0, reason="already_up")
        return base

    assert_browser_launch_allowed(
        component="scripts.browser.agent.cdp_launcher", action="cdp_scheduler_start"
    )

    if not is_task_registered(task_name):
        L2("CDP_BOOT_FAIL", ACTOR, reason="task_not_registered", task=task_name)
        raise RuntimeError(
            f"Task '{task_name}' 미등록. 다음 명령으로 등록 필요:\n"
            f"  powershell -ExecutionPolicy Bypass -File "
            f"scripts/browser/cdp/install_cdp_chrome_task.ps1"
        )

    ok, msg = start_via_scheduler(task_name)
    if not ok:
        L2("CDP_BOOT_FAIL", ACTOR, reason="schtasks_run_failed", message=msg[:500])
        raise RuntimeError(f"schtasks /run 실패: {msg}")

    deadline = time.time() + timeout
    retries = 0
    while time.time() < deadline:
        retries += 1
        if probe_cdp(host, port):
            L2("CDP_BOOT_OK", ACTOR, host=host, port=port, retries=retries, total_ms=int((time.time() - t0) * 1000))
            return base
        time.sleep(PROBE_INTERVAL)

    L2("CDP_BOOT_FAIL", ACTOR, reason="probe_timeout", retries=retries, total_ms=int((time.time() - t0) * 1000))
    raise RuntimeError(f"CDP {base} 응답 없음 ({timeout}초 대기). Chrome 기동 확인 필요.")


def open_url(url: str, host: str = CDP_HOST, port: int = CDP_PORT, activate: bool = True) -> dict:
    """CDP API로 현재 Chrome에 새 탭 열기 — 사용자 수동 입력 불필요.

    /json/new?<url> PUT 호출로 즉시 새 탭이 열리고 활성화됨.
    Chrome 창이 백그라운드에 있어도 자동으로 전면화.

    사용 예 (CLI):
        python -m scripts.browser.agent.cdp_launcher https://example.com
    """
    ensure_cdp(host=host, port=port)
    # URL이 스킴 없으면 https:// 자동 부여
    if not url.startswith(("http://", "https://", "about:", "file://", "chrome://")):
        url = "https://" + url
    api = f"http://{host}:{port}/json/new?{url}"
    req = urllib.request.Request(api, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            import json as _json

            tab = _json.loads(r.read().decode("utf-8"))
        L2("CDP_OPEN_TAB", ACTOR, url=url, tab_id=tab.get("id", "")[:20])
        return tab
    except Exception as e:
        L2("CDP_OPEN_TAB_FAIL", ACTOR, url=url, error=str(e)[:300])
        raise RuntimeError(f"새 탭 열기 실패: {e}") from e


def open_and_wait_login(
    url: str,
    domain: str | None = None,
    timeout: int = 300,
) -> dict:
    """탭 열기 + 로그인 자동 감지 통합 헬퍼.

    Args:
        url: 열 사이트 URL
        domain: 로그인 감시 도메인. None이면 url에서 자동 추출
        timeout: 로그인 대기 최대 시간(초)

    Returns:
        {"tab": {...}, "logged_in": bool, "elapsed_s": int}
    """
    from scripts.browser.agent.cdp_session_manager import (
        is_logged_in,
        wait_for_login,
    )

    if domain is None:
        from urllib.parse import urlparse

        host_part = urlparse(url if "://" in url else f"https://{url}").hostname or ""
        # www. 제거
        domain = host_part[4:] if host_part.startswith("www.") else host_part

    tab = open_url(url)
    t0 = time.time()
    if is_logged_in(domain):
        return {"tab": tab, "logged_in": True, "elapsed_s": 0, "already": True}

    ok = wait_for_login(domain, timeout=timeout)
    return {
        "tab": tab,
        "logged_in": ok,
        "elapsed_s": int(time.time() - t0),
        "already": False,
    }


if __name__ == "__main__":
    # CLI: python -m ...cdp_launcher <url> [--wait-login [domain] [timeout_s]]
    import sys

    args = sys.argv[1:]
    if not args:
        print(
            "Usage: python -m scripts.browser.agent.cdp_launcher <url> "
            "[--wait-login [domain] [timeout_s]]"
        )
        sys.exit(1)
    target_url = args[0]
    if "--wait-login" in args:
        idx = args.index("--wait-login")
        rest = args[idx + 1 :]
        dom = rest[0] if len(rest) >= 1 else None
        to = int(rest[1]) if len(rest) >= 2 else 300
        result = open_and_wait_login(target_url, domain=dom, timeout=to)
        print(f"OPENED: {result['tab'].get('url', '')}")
        print(
            f"LOGGED_IN: {result['logged_in']}  "
            f"(already={result.get('already', False)}, "
            f"elapsed={result['elapsed_s']}s)"
        )
    else:
        tab = open_url(target_url)
        print(f"OPENED: {tab.get('url', '')}")
