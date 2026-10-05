"""CDP Chrome 수명주기 보조 — 깨끗하게 시작하고, 로그인은 유지하고, 정상 종료한다.

배경(2026-10-05): 데몬이 Chrome 을 다시 띄울 때마다 어제 자동화가 열어 둔 YouTube·Gmail 탭이 되살아났고, 반대로 네이버 로그인 쿠키는 사라져 있었다.
실제 Chrome(임시 프로필·로컬 가짜 사이트)으로 비교한 결과:
- 로그인 유지: 세션 쿠키(만료 없는 로그인 쿠키)는 `--restore-last-session` **스위치**로 이전 세션을 복원해 열고 **정상 종료**했을 때만 재시작 뒤에도 남았다.
  기본 설정은 쿠키가 사라졌고, Preferences 파일에 "이어서 열기"를 써 넣는 방식은 Chrome 이 무시했다(시작 설정은 변조 방지로 보호됨), 강제 종료도 쿠키가 사라졌다.
  쿠키 값은 건드리지 않는다 — 브라우저의 표준 스위치·종료 명령만 쓴다. (이 스위치는 값과 무관하게 있으면 켜진다 — `=false` 를 붙이면 안 된다.)
- 깨끗한 시작: 복원된 옛 탭은 시작 직후 닫고 빈 탭 하나만 남긴다(사용자가 실행 중에 연 탭은 건드리지 않는다).
- 정상 종료: CDP `Browser.close` 로 먼저 닫아 쿠키·세션이 디스크에 남게 하고, 안 닫히면 그때 강제 종료한다.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import time
from typing import Any

RESTORE_SWITCH = "--restore-last-session"  # Chrome 실행 인자(값 없이). 이전 세션 복원 → 세션 쿠키(로그인) 유지
CLOSE_WAIT_S = 8.0
RESTORE_SETTLE_S = 2.5  # 시작 직후 세션 복원이 끝나기를 기다리는 시간


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


def close_stale_tabs(port: int, *, settle_s: float = RESTORE_SETTLE_S, sleep=time.sleep) -> int:
    """시작 직후 복원된 옛 탭을 모두 닫고 빈 탭 하나만 남긴다 → 닫은 개수. 실패해도 예외를 내지 않는다(브라우저 시작을 막지 않는다)."""
    try:
        sleep(settle_s)
        old = page_tab_ids(_http(port, "/json/list"))
        if not old:
            return 0
        _http(port, "/json/new?about:blank", method="PUT")  # 마지막 탭을 닫으면 Chrome 이 끝나므로 빈 탭을 먼저 만든다
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
