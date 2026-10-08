"""scripts/browser/agent/electron_target.py — Electron 앱 자신의 창(webview
포함)을 CDP로 제어하기 위한 어댑터.

목적
====
Electron 앱을 `--remote-debugging-port`로 띄우면(admin-web/electron/main.js) webview
콘텐츠도 CDP target으로 노출된다 — 2026-09-28 실측 확인: `GET /json/list`에
`{"type": "webview", "url": "http://127.0.0.1:3000/", "webSocketDebuggerUrl": "..."}`
항목이 정상적으로 잡힘. 하지만 Playwright의 `chromium.connect_over_cdp()`는 "page" 타입
target만 `browser.contexts[0].pages`에 노출한다(같은 날 실측 확인 — webview는 안 보임).

이 모듈은 그 webview target의 websocket에 raw CDP JSON-RPC로 직접 붙어,
universal_actions.py가 기대하는 최소 인터페이스(`.context.new_cdp_session()`,
`.goto()`, `.keyboard.press()/type()`, `.screenshot()`, `.url`)를 흉내내는 어댑터
(ElectronTargetPage)를 제공한다 — universal_actions.py 자체는 한 글자도 수정하지
않는다. Playwright page든 이 어댑터든 snapshot()/act()/navigate()가 그대로 동작한다.

한계 (1단계, 문서화된 제약)
====
- `keyboard.press()`는 no-op이다. Control+A 같은 조합키는 CDP
  `Input.dispatchKeyEvent`에 정확한 key/code/windowsVirtualKeyCode 매핑이 더
  필요해 이번엔 생략했다 — act(..., "fill", ...)는 이 타겟에서는 "덮어쓰기"가
  아니라 "이어붙이기"로 동작한다.
- 대상은 admin-web(내 앱 UI) 전용으로 설계했다. 임의 외부 사이트는
  기존 경로(cdp.py + universal_actions.py, 사용자 Chrome 포트 9222)를 그대로 쓴다.

근거
====
Electron 공식 문서(--remote-debugging-port, electronjs.org/docs/latest/api/
command-line-switches — app.whenReady() 이전에 app.commandLine.appendSwitch로 설정).
CDP 표준 웹소켓 JSON-RPC 프레이밍({"id","method","params"} 요청 /
{"id","result"|"error"} 응답)은 scripts/cdp_helper.py의 기존 구현과 같은 규약이다
(그 파일을 확장하지 않고 새로 작성 — docs/specs/2026-09-28_..._trigger.md §3 결정 유지).
websocket-client 공식 문서(threading.html): recv() 루프와 send() 호출을 서로 다른
스레드에서 쓰므로 create_connection(..., enable_multithread=True) 필수(2026-09-28 확인,
안 주면 비동기 동작이라 스레드 안전하지 않음).
"""

from __future__ import annotations

import base64
import contextlib
import json
import threading
import time
import urllib.request
from typing import Any

import websocket  # pip install websocket-client (requirements.txt에 이미 있음)

DEFAULT_ELECTRON_CDP_PORT = 9333


class ElectronTargetError(RuntimeError):
    """Electron CDP 타겟 연결/탐색/통신 실패."""


def list_electron_targets(port: int = DEFAULT_ELECTRON_CDP_PORT, timeout: float = 3.0) -> list[dict]:
    """Electron 앱의 CDP 타겟 목록(webview 포함)을 조회한다."""
    url = f"http://127.0.0.1:{port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:  # 로컬호스트 CDP 엔드포인트만 조회
            return json.loads(res.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ElectronTargetError(
            f"Electron CDP 포트({port})에 연결할 수 없습니다 — 앱이 실행 중이고 "
            f"--remote-debugging-port={port} 가 설정됐는지 확인하세요."
        ) from e


def _find_target(targets: list[dict], url_contains: str) -> dict:
    for t in targets:
        if t.get("type") == "webview" and url_contains in (t.get("url") or ""):
            return t
    for t in targets:  # webview를 못 찾으면 page 타입도 허용(단일 창 구성일 때 폴백)
        if t.get("type") == "page" and url_contains in (t.get("url") or ""):
            return t
    urls = [t.get("url") for t in targets]
    raise ElectronTargetError(f"{url_contains!r}를 포함하는 CDP 타겟을 못 찾음: {urls}")


class _RawCDPSession:
    """단일 CDP target에 대한 websocket JSON-RPC 세션.

    Playwright `CDPSession.send()`와 같은 계약(메서드명+params -> 결과 dict를 그대로
    반환, `{"result": ...}` 래핑 없이)을 지킨다 — universal_actions.py가 Playwright의
    CDPSession과 이 클래스를 구분하지 않고 쓸 수 있게 하기 위함.
    """

    def __init__(self, ws_url: str) -> None:
        # enable_multithread=True 필수 — recv 루프(리더 스레드)와 send(호출 스레드)를
        # 동시에 쓰므로(websocket-client 공식 문서, threading.html 확인).
        self._ws = websocket.create_connection(ws_url, timeout=15, suppress_origin=True, enable_multithread=True)
        self._seq = 0
        self._lock = threading.Lock()
        self._results: dict[int, dict] = {}
        self._alive = True
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

    def _reader(self) -> None:
        while self._alive:
            try:
                raw = self._ws.recv()
                if not raw:
                    break
                msg = json.loads(raw)
                mid = msg.get("id")
                if mid is not None:
                    with self._lock:
                        self._results[mid] = msg
            except Exception:  # noqa: BLE001 - CDP 리더 스레드: 연결 종료/파싱 실패 시 루프만 빠져나감(best-effort, 호출측은 send()의 타임아웃으로 실패를 감지)
                break

    def send(self, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> dict:
        with self._lock:
            self._seq += 1
            mid = self._seq
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                msg = self._results.pop(mid, None)
            if msg is not None:
                if "error" in msg:
                    raise ElectronTargetError(f"CDP 오류 {method}: {msg['error']}")
                return msg.get("result", {})
            time.sleep(0.02)
        raise ElectronTargetError(f"CDP 응답 타임아웃({timeout}s): {method}")

    def close(self) -> None:
        """진짜 websocket 연결을 끊는다 — ElectronTargetPage.close()에서만 호출."""
        self._alive = False
        with contextlib.suppress(Exception):  # 종료 시 소켓 close 실패는 무시해도 안전(이미 끊긴 연결일 수 있음)
            self._ws.close()


class _CDPSessionHandle:
    """new_cdp_session() 이 호출마다 돌려주는 얇은 핸들.

    Playwright 의미상 `new_cdp_session()`은 호출할 때마다 새 논리 세션을 주고,
    그 세션의 detach()는 그 세션만 끊지 실제 브라우저 연결 자체는 안 죽인다.
    이 어댑터는 target 당 websocket 연결이 하나뿐이라 모든 호출이 같은 연결을
    공유하므로, detach()를 no-op으로 둬서 그 의미를 맞춘다 — universal_actions.py가
    매 snapshot()/act() 호출 끝에 `finally: cdp.detach()`를 부르는데, 여기서 실제로
    연결을 끊으면 바로 다음 호출이 끊긴 소켓에 쓰려다 실패한다(2026-09-28 실기 검증
    중 발견·수정: click 전 snapshot()의 detach()가 연결을 끊어 act()가 즉시 깨졌었음).
    진짜 종료는 ElectronTargetPage.close()로만 한다.
    """

    def __init__(self, session: _RawCDPSession) -> None:
        self._session = session

    def send(self, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> dict:
        return self._session.send(method, params, timeout)

    def detach(self) -> None:
        pass  # 공유 연결이라 여기서 끊지 않는다 — 위 클래스 docstring 참고


class _KeyboardAdapter:
    """page.keyboard의 최소 흉내 — universal_actions.py가 쓰는 press()/type()만 구현."""

    def __init__(self, session: _RawCDPSession) -> None:
        self._session = session

    def press(self, _key: str) -> None:
        # 콤보키(Control+A 등) 미지원 — 모듈 docstring "한계" 참고. no-op.
        pass

    def type(self, text: str) -> None:  # Playwright API 이름 그대로(자체 규칙 예외 아님)
        self._session.send("Input.insertText", {"text": text})


class ElectronTargetPage:
    """universal_actions.py가 기대하는 최소 Playwright Page 인터페이스 어댑터."""

    def __init__(self, ws_url: str, url: str) -> None:
        self._session = _RawCDPSession(ws_url)
        self.url = url
        self.keyboard = _KeyboardAdapter(self._session)

    @property
    def context(self) -> ElectronTargetPage:
        return self  # new_cdp_session(page) 하나만 있으면 되므로 self를 context로도 노출

    def new_cdp_session(self, _page: Any) -> _CDPSessionHandle:
        return _CDPSessionHandle(self._session)

    def close(self) -> None:
        """실제 websocket 연결을 끊는다. universal_actions.py는 호출하지 않는다 —
        호출측(MCP 서버 등)이 이 타겟을 완전히 끝낼 때만 명시적으로 부른다."""
        self._session.close()

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> None:
        self._session.send("Page.navigate", {"url": url})
        self.url = url

    def screenshot(self) -> bytes:
        self._session.send("Page.enable")  # captureScreenshot 전에 Page 도메인 활성화 필요(실측 확인)
        result = self._session.send("Page.captureScreenshot", {"format": "png"})
        return base64.b64decode(result.get("data", ""))


def connect_electron_webview(
    *, port: int = DEFAULT_ELECTRON_CDP_PORT, url_contains: str = "127.0.0.1:3000"
) -> ElectronTargetPage:
    """Electron 앱의 webview(기본: admin-web, 127.0.0.1:3000) target에 CDP로 접속한다."""
    targets = list_electron_targets(port)
    target = _find_target(targets, url_contains)
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise ElectronTargetError(f"타겟에 webSocketDebuggerUrl 없음: {target}")
    return ElectronTargetPage(ws_url, target.get("url", ""))
