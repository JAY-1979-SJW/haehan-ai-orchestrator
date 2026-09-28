"""특정 탭 ID를 지정해서 붙는 CDP 헬퍼 — cdp_helper.CDP는 항상 첫 탭에 붙어서
공유 브라우저에서 다른 작업 중인 탭을 건드리는 사고가 있었음(2026-09-11).
이 헬퍼는 반드시 새로 만든 탭 ID로만 붙는다.
"""

import base64
import contextlib
import json
import threading
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[2]
SHOT_PATH = ROOT / "data" / "browser_screenshot_tab.png"


class TabCDP:
    def __init__(self, port: int, tab_id: str):
        self._port = port
        self._tab_id = tab_id
        self._pending: dict = {}
        self._results: dict = {}
        self._lock = threading.Lock()
        self._seq = 0
        self._alive = True
        ws_url = f"ws://127.0.0.1:{port}/devtools/page/{tab_id}"
        self._ws = websocket.create_connection(ws_url, timeout=None, suppress_origin=True)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while self._alive:
            try:
                raw = self._ws.recv()
            except Exception:  # noqa: BLE001 - CDP 탭 제어용 WebSocket 클라이언트 내부 유틸 — 수신루프 실패는 break로 종료, JSON파싱 실패는 continue, 연결 종료(close) 실패는 무시할 뿐 쓰기 없음
                break
            try:
                msg = json.loads(raw)
            except Exception:  # noqa: BLE001 - CDP 탭 제어용 WebSocket 클라이언트 내부 유틸 — 수신루프 실패는 break로 종료, JSON파싱 실패는 continue, 연결 종료(close) 실패는 무시할 뿐 쓰기 없음
                continue
            if "id" in msg:
                with self._lock:
                    self._results[msg["id"]] = msg

    def send(self, method: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        with self._lock:
            self._seq += 1
            mid = self._seq
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if mid in self._results:
                    return self._results.pop(mid)
            time.sleep(0.05)
        return {}

    def navigate(self, url: str, wait: float = 3.0):
        self.send("Page.navigate", {"url": url})
        time.sleep(wait)

    def js(self, expr: str):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, 20)
        return r.get("result", {}).get("result", {}).get("value")

    def shot(self, label: str = "") -> bool:
        r = self.send("Page.captureScreenshot", {"format": "png", "quality": 80}, 10)
        data = r.get("result", {}).get("data", "")
        if data:
            SHOT_PATH.write_bytes(base64.b64decode(data))
            if label:
                print(f"  [📷] {label}")
            return True
        print(f"  [📷] 캡처 실패: {label}")
        return False

    def click(self, x: float, y: float):
        self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        self.send(
            "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}
        )
        self.send(
            "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}
        )

    def type_text(self, text: str):
        self.send("Input.insertText", {"text": text})

    def close(self):
        self._alive = False
        # WebSocket 연결 close() 실패는 무시 — 이미 종료 중인 리소스 정리 실패일 뿐
        with contextlib.suppress(Exception):
            self._ws.close()


def new_tab(port: int, url: str) -> str:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read())
    return data["id"]


def close_tab(port: int, tab_id: str):
    urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{tab_id}", timeout=10)
