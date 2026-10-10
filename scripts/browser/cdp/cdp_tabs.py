"""CDP 새 탭 안전 열기 — `about:blank` 로 남지 않고, 남의 탭을 덮어쓰지 않는다.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md §9-3
실측(2026-10-02): Playwright `ctx.new_page()` 는 `about:blank` 로 만든 뒤 `goto` 가 20초 타임아웃으로 멈췄다.
같은 브라우저에서 `PUT /json/new?<주소>` 는 3초 안에 이동했다 → 이 모듈은 Playwright 로 탭을 만들지 않는다(HTTP 만 사용).

규칙
1. **주소와 함께 만든다**(빈 탭 단계 없음). 도착(비어 있지 않고 오류 페이지가 아님)을 확인하고, 실패하면 **그 탭을 닫고** 재시도한다.
2. **소유권**: 이 모듈이 만든 탭만 닫을 수 있다(사용자 탭·로그인 탭 불가침 — 로그인 세션 보존 원칙).
3. 칸(lane)은 `scripts/cdp_lanes` 등록표로 정한다. 그 칸의 Chrome 이 꺼져 있으면 오류(여기서 켜지 않는다).
"""

from __future__ import annotations

import contextlib
import http.client
import json
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from scripts.browser.cdp import cdp_lanes

DEFAULT_WAIT_SEC = 10.0
POLL_SEC = 0.3
_BLANK_PREFIXES = ("about:blank", "chrome://newtab", "chrome-search://")
_ERROR_PREFIXES = ("chrome-error://",)


class CdpTabError(RuntimeError):
    """새 탭 열기·닫기 실패."""


class LaneDown(CdpTabError):
    """그 칸의 Chrome 이 꺼져 있다."""


class NotOwned(CdpTabError):
    """이 모듈이 만든 탭이 아니다(남의 탭은 닫지 않는다)."""


@dataclass(frozen=True)
class TabHandle:
    tab_id: str
    lane: str
    url: str
    reason: str
    ws_url: str = ""


_lock = threading.Lock()
_owned: dict[tuple[str, str], str] = {}  # (칸, 탭 id) → 만든 이유


class _HttpStatus(OSError):
    """CDP HTTP 가 오류 상태 코드를 돌려줌."""

    def __init__(self, code: int, path: str) -> None:
        super().__init__(f"CDP HTTP {code}: {path}")
        self.code = code


def _http(lane: cdp_lanes.Lane, method: str, path: str, timeout: float = 5.0) -> Any:
    """로컬 CDP(127.0.0.1) 고정 호스트로 HTTP 한 번. 임의 주소를 열지 않으므로 urllib 대신 http.client 로 연결한다."""
    conn = http.client.HTTPConnection(cdp_lanes.CDP_HOST, lane.port, timeout=timeout)
    try:
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read()
        if resp.status >= 400:
            raise _HttpStatus(resp.status, path.split("?")[0])
    finally:
        conn.close()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body.decode("utf-8", "replace")


def list_tabs(lane_name: str = cdp_lanes.GENERAL) -> list[dict[str, Any]]:
    """그 칸의 탭 목록(읽기 전용). 각 항목에 `owned_reason`(이 모듈이 만든 탭이면 이유, 아니면 빈 문자열) 포함."""
    lane = cdp_lanes.get_lane(lane_name)
    try:
        tabs = _http(lane, "GET", "/json/list")
    except OSError as e:
        raise LaneDown(f"CDP 칸 '{lane_name}'(포트 {lane.port})이 응답하지 않습니다") from e
    out = []
    for t in tabs or []:
        if t.get("type") != "page":
            continue
        out.append({**t, "owned_reason": _owned.get((lane_name, t.get("id", "")), "")})
    return out


def _arrived(url: str) -> bool:
    return bool(url) and not url.startswith(_BLANK_PREFIXES) and not url.startswith(_ERROR_PREFIXES)


def probe_page(ws_url: str, timeout: float = 3.0) -> tuple[str, str]:
    """탭 안의 **실제** 상태 `(location.href, document.readyState)`. 탭 목록(`/json/list`)의 주소·제목은 이동 완료 신호가 아니다
    (실측 2026-10-02: 목록은 이동 전에 목표 주소·방문 기록 제목을 미리 보여 주고 탭 안은 약 2초간 about:blank 였다)."""
    import websocket  # 의존성: websocket-client(requirements.txt)

    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "JSON.stringify([location.href, document.readyState])", "returnByValue": True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                value = msg.get("result", {}).get("result", {}).get("value")
                href, ready = json.loads(value) if value else ("", "")
                return str(href), str(ready)
    finally:
        ws.close()


def _create(lane: cdp_lanes.Lane, url: str) -> dict[str, Any]:
    # Chrome 은 `/json/new?<주소>` 를 PUT 으로 받는다(구버전은 GET). 주소 안의 ?·&·# 은 그대로 둔다.
    target = urllib.parse.quote(url, safe=":/?&=#%@+,;~")
    try:
        return _http(lane, "PUT", f"/json/new?{target}")
    except _HttpStatus as e:
        if e.code != 405:
            raise
        return _http(lane, "GET", f"/json/new?{target}")


def _close_quietly(lane: cdp_lanes.Lane, tab_id: str) -> None:
    with contextlib.suppress(OSError):  # 이미 닫혔거나 칸이 꺼짐 — 정리 실패는 결과에 영향 없음
        _http(lane, "GET", f"/json/close/{tab_id}", timeout=3.0)


def open_tab(  # noqa: PLR0913 - 칸·이유·대기·재시도·시계 주입은 모두 호출부가 정하는 독립 옵션
    url: str,
    *,
    lane: str = cdp_lanes.GENERAL,
    reason: str,
    wait_sec: float = DEFAULT_WAIT_SEC,
    retries: int = 1,
    probe: Callable[[str], tuple[str, str]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> TabHandle:
    """주소를 가진 새 탭을 만들고 도착을 확인한다. 실패하면 만든 탭을 닫고 재시도, 끝내 안 되면 `CdpTabError`."""
    if not reason.strip():
        raise ValueError("reason(작업 이름)이 필요합니다 — 어떤 작업이 연 탭인지 기록한다")
    if not url.startswith(("http://", "https://")):
        raise ValueError("http(s) 주소만 열 수 있습니다")
    lane_obj = cdp_lanes.get_lane(lane)
    last_error = ""
    for attempt in range(retries + 1):
        try:
            created = _create(lane_obj, url)
        except OSError as e:
            raise LaneDown(f"CDP 칸 '{lane}'(포트 {lane_obj.port})이 응답하지 않습니다") from e
        tab_id = str((created or {}).get("id", ""))
        if not tab_id:
            last_error = "탭 id 를 받지 못했습니다"
            continue
        with _lock:
            _owned[(lane, tab_id)] = reason  # 만든 즉시 소유로 기록 — 실패 정리 때도 우리 탭임을 안다
        ws_url = str((created or {}).get("webSocketDebuggerUrl", ""))
        check = probe or probe_page
        deadline = clock() + wait_sec
        current = ""
        while clock() < deadline:
            try:
                current, ready = check(ws_url) if ws_url else ("", "")
            except Exception:  # noqa: BLE001 - 소켓이 아직 안 열렸거나 탭이 이동 중 — 다음 확인 때 다시 본다
                current, ready = "", ""
            if _arrived(current) and ready in ("interactive", "complete"):
                return TabHandle(tab_id, lane, current, reason, ws_url)  # 탭 안의 실제 페이지가 떴다
            if current.startswith(_ERROR_PREFIXES):
                break  # 오류 페이지는 기다려도 나아지지 않는다
            sleep(POLL_SEC)
        last_error = f"{wait_sec:g}초 안에 페이지가 뜨지 않음(탭 안 주소 {current or '확인 불가'}), 시도 {attempt + 1}/{retries + 1}"
        _close_quietly(lane_obj, tab_id)
        with _lock:
            _owned.pop((lane, tab_id), None)
    hint = " — 같은 칸의 다른 사이트는 열리는데 이 사이트만 안 열리면 오래 켜 둔 브라우저 세션 문제일 수 있음(프로필 유지 재시작 권장, 2026-10-02 사례)"
    raise CdpTabError(f"새 탭 열기 실패: {last_error}{hint}")


def close_tab(handle: TabHandle) -> None:
    """이 모듈이 만든 탭만 닫는다."""
    key = (handle.lane, handle.tab_id)
    with _lock:
        if key not in _owned:
            raise NotOwned(f"탭 {handle.tab_id[:6]} 는 이 모듈이 만든 탭이 아니어서 닫지 않습니다")
        del _owned[key]
    _close_quietly(cdp_lanes.get_lane(handle.lane), handle.tab_id)


def close_owned(lane: str | None = None, reason: str | None = None) -> int:
    """이 프로세스가 만든 탭을 모두 닫는다(작업 종료·실패 정리용). 사용자 탭은 건드리지 않는다."""
    with _lock:
        targets = [
            (k, r) for k, r in _owned.items() if (lane is None or k[0] == lane) and (reason is None or r == reason)
        ]
        for key, _ in targets:
            del _owned[key]
    for (lane_name, tab_id), _ in targets:
        _close_quietly(cdp_lanes.get_lane(lane_name), tab_id)
    return len(targets)


def owned_count() -> int:
    with _lock:
        return len(_owned)
