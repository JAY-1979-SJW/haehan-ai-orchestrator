"""CDP Chrome 수명주기 보조 — 깨끗하게 시작하고, 로그인은 유지하고, 정상 종료한다.

배경(2026-10-05): 데몬이 Chrome 을 다시 띄울 때마다 어제 자동화가 열어 둔 YouTube·Gmail 탭이 되살아났고, 반대로 네이버 로그인 쿠키는 사라져 있었다.
실제 Chrome(임시 프로필·로컬 가짜 사이트)으로 비교한 결과:
- 로그인 유지: 세션 쿠키(만료 없는 로그인 쿠키)는 `--restore-last-session` **스위치**로 이전 세션을 복원해 열고 **정상 종료**했을 때만 재시작 뒤에도 남았다.
  기본 설정은 쿠키가 사라졌고, Preferences 파일에 "이어서 열기"를 써 넣는 방식은 Chrome 이 무시했다(시작 설정은 변조 방지로 보호됨), 강제 종료도 쿠키가 사라졌다.
  쿠키 값은 건드리지 않는다 — 브라우저의 표준 스위치·종료 명령만 쓴다. (이 스위치는 값과 무관하게 있으면 켜진다 — `=false` 를 붙이면 안 된다.)
- 깨끗한 시작: 복원된 옛 탭은 시작 직후 닫고 빈 탭 하나만 남긴다(사용자가 실행 중에 연 탭은 건드리지 않는다).
- 정상 종료: CDP `Browser.close` 로 먼저 닫아 쿠키·세션이 디스크에 남게 하고, 안 닫히면 종료 신호 → 강제 종료 순으로 넘어간다.
  실측: **로그인 쿠키까지 남는 것은 CDP `Browser.close` 뿐**이다. 종료 신호(Windows 창 닫기 요청)는 탭은 복원되지만 세션 쿠키는 사라졌고, 강제 종료는 둘 다 잃었다.
  그래서 2·3단계는 프로세스를 확실히 끝내는 안전망일 뿐 로그인 보존을 보장하지 않는다(호출자는 `graceful` 이 아니면 경고를 남긴다).
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

RESTORE_SWITCH = "--restore-last-session"  # Chrome 실행 인자(값 없이). 이전 세션 복원 → 세션 쿠키(로그인) 유지
CLOSE_WAIT_S = 8.0
RESTORE_SETTLE_S = 10.0  # 시작 직후 세션 복원이 끝나기를 기다리는 최대 시간(탭 목록이 두 번 연속 같으면 끝난 것으로 본다)
RESTORE_POLL_S = 0.7
SIGNAL_WAIT_S = 5.0


def page_tab_ids(tabs: list[dict[str, Any]]) -> list[str]:
    """`/json/list` 결과에서 page 탭 id 만(확장·워커·브라우저 UI 제외)."""
    return [str(t["id"]) for t in tabs if t.get("type") == "page" and t.get("id")]


def _http(port: int, path: str, method: str = "GET", timeout: float = 5.0) -> Any:
    """로컬 CDP(127.0.0.1) HTTP 호출. 고정 주소만 연다."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path)
        body = conn.getresponse().read()
    finally:
        conn.close()
    try:
        return json.loads(body)
    except ValueError:
        return body.decode("utf-8", errors="replace")


def _wait_restore_settled(port: int, *, timeout_s: float, poll_s: float, sleep, clock) -> list[str]:
    """복원이 끝나기를 기다린다: page 탭 목록이 두 번 연속 같으면(또는 시간 초과) 그 목록을 돌려준다. 탭이 많아도 고정 대기보다 정확하다."""
    deadline = clock() + timeout_s
    last: list[str] | None = None
    same = 0
    while True:
        ids = sorted(page_tab_ids(_http(port, "/json/list")))
        same = same + 1 if ids == last else 0
        last = ids
        if same >= 2 or clock() >= deadline:
            return ids
        sleep(poll_s)


BLANK_URL = "about:blank"


def _safe_start_url(url: str) -> str:
    """시작 탭 주소: http(s) 또는 about:blank 만 허용한다(그 밖의 스킴·공백·제어문자는 빈 탭으로 대체)."""
    ok = url == BLANK_URL or (url.startswith(("http://", "https://")) and not any(ch.isspace() or ord(ch) < 32 for ch in url))
    return url if ok else BLANK_URL


def close_stale_tabs(
    port: int,
    *,
    start_url: str = BLANK_URL,
    settle_s: float = RESTORE_SETTLE_S,
    poll_s: float = RESTORE_POLL_S,
    sleep=time.sleep,
    clock=time.monotonic,
) -> int:
    """시작 직후 복원된 옛 탭을 모두 닫고 `start_url` 탭 하나만 남긴다(기본 빈 탭) → 닫은 개수. 실패해도 예외를 내지 않는다(브라우저 시작을 막지 않는다)."""
    try:
        old = _wait_restore_settled(port, timeout_s=settle_s, poll_s=poll_s, sleep=sleep, clock=clock)
        if not old:
            return 0
        _http(port, f"/json/new?{_safe_start_url(start_url)}", method="PUT")  # 마지막 탭을 닫으면 Chrome 이 끝나므로 시작 탭을 먼저 만든다
        closed = 0
        for tab_id in old:
            with contextlib.suppress(Exception):
                _http(port, f"/json/close/{tab_id}")
                closed += 1
        return closed
    except Exception:  # noqa: BLE001 - 정리는 부가 기능: 브라우저·데몬 동작을 막지 않는다
        return 0


def graceful_close(
    port: int, *, is_alive, timeout_s: float = CLOSE_WAIT_S, sleep=time.sleep, clock=time.monotonic
) -> bool:
    """CDP `Browser.close` 로 정상 종료를 요청하고 `is_alive()` 가 False 가 될 때까지 기다린다 → 정상 종료됐으면 True.

    False 면 호출자가 강제 종료로 넘어간다. 브라우저가 멈췄거나 포트가 닫혀 있으면 곧바로 False.
    """
    try:
        import websocket

        ws_url = _http(port, "/json/version", timeout=3).get("webSocketDebuggerUrl")
        if not ws_url:
            return False
        ws = websocket.create_connection(ws_url, timeout=3)
        try:
            ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
        finally:
            with contextlib.suppress(Exception):
                ws.close()
    except Exception:  # noqa: BLE001 - 정상 종료를 못 하면 호출자가 강제 종료한다
        return False
    deadline = clock() + timeout_s
    while clock() < deadline:
        if not is_alive():
            return True
        sleep(0.3)
    return not is_alive()


def _polite_signal(pid: int, *, is_alive, timeout_s: float = SIGNAL_WAIT_S, sleep=time.sleep, clock=time.monotonic) -> bool:
    """2단계: 종료 신호(Windows 는 강제 옵션 없는 taskkill = 창 닫기 요청, 그 밖에는 SIGTERM). ChromeDriver 의 quitGracefully 와 같은 순서."""
    try:
        if sys.platform == "win32":
            taskkill = shutil.which("taskkill")  # 시스템 명령을 PATH 에서 찾는다(없으면 신호 단계를 건너뛴다)
            if not taskkill:
                return False
            subprocess.run([taskkill, "/PID", str(int(pid))], capture_output=True, timeout=10, check=False)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        return False
    deadline = clock() + timeout_s
    while clock() < deadline:
        if not is_alive():
            return True
        sleep(0.3)
    return not is_alive()


def _force_kill(pid: int) -> None:
    import psutil

    with contextlib.suppress(psutil.Error):
        psutil.Process(pid).kill()


def _pid_alive(pid: int) -> bool:
    import psutil

    return psutil.pid_exists(pid)


def stop_browser(port: int, pid: int, *, is_alive=None, graceful=graceful_close, polite=_polite_signal, force=_force_kill) -> str:
    """Chrome 을 3단계로 닫는다 → 끝난 방식(`already_stopped`·`graceful`·`signal`·`forced`).

    1) CDP `Browser.close` — 쿠키·세션이 디스크에 남는다(로그인 유지는 이 단계뿐)  2) 종료 신호 — 탭은 복원되지만 로그인 쿠키는 잃을 수 있다
    3) 강제 종료(마지막 수단 — 둘 다 잃을 수 있다).
    """
    alive = is_alive or (lambda: _pid_alive(pid))
    if not alive():
        return "already_stopped"
    if graceful(port, is_alive=alive):
        return "graceful"
    if polite(pid, is_alive=alive):
        return "signal"
    force(pid)
    return "forced"
