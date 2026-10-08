"""CDP 공통 헬퍼 — 백그라운드 스레드로 이벤트 범람 처리.

apps/marketing-standalone/connectors/cdp_helper.py 는 이 파일의 사본(독립배포 앱이라
scripts/ 를 import 할 수 없어 부득이하게 복제 — docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md
§3 참고). 2026-09-29 정리에서 그 사본이 먼저 넣었던 개선 2건(urlopen 타임아웃,
예외 디버그 로깅)을 이쪽 원본에 역이식해 두 사본을 다시 동일하게 맞춤.
"""

import base64
import json
import logging
import threading
import time
import urllib.request

import websocket

from scripts.common.app_paths import repo_root

ROOT = repo_root()
SHOT_PATH = ROOT / "data" / "browser_screenshot.png"
_log = logging.getLogger(__name__)


class CDP:
    def __init__(self, port: int = 9222):
        self._port = port
        self._pending: dict = {}
        self._results: dict = {}
        self._callbacks: dict = {}
        self._lock = threading.Lock()
        self._seq = 0
        self._alive = True
        self._ws = self._connect()
        threading.Thread(target=self._reader, daemon=True).start()

    def _get_ws_url(self) -> str:
        with urllib.request.urlopen(f"http://127.0.0.1:{self._port}/json", timeout=5) as r:
            tabs = json.loads(r.read())
        page_tab = next((t for t in tabs if t.get("type") == "page"), tabs[0])
        return page_tab["webSocketDebuggerUrl"]

    def _connect(self):
        return websocket.create_connection(self._get_ws_url(), timeout=None, suppress_origin=True)

    def _reconnect(self):
        """연결이 끊기면 재연결."""
        for _ in range(5):
            try:
                time.sleep(0.5)
                self._ws = self._connect()
                return True
            except Exception as e:  # noqa: BLE001 - CDP 웹소켓 연결 헬퍼(원본) — 재연결 재시도, 이벤트 콜백 실패 무시, 종료 시 소켓 close 실패 무시 등 모두 best-effort 브라우저 자동화 인프라, 실패해도 재연결 루프로 복구됨.
                _log.debug("CDP 재연결 시도 실패(무시): %s", e)
        return False

    def on(self, method: str, callback):
        """CDP 이벤트 콜백 등록. callback(params) 형태."""
        with self._lock:
            self._callbacks[method] = callback

    def off(self, method: str):
        with self._lock:
            self._callbacks.pop(method, None)

    def _reader(self):
        while self._alive:
            try:
                raw = self._ws.recv()
                if not raw:  # 빈 문자열 = 연결 종료
                    raise EOFError("empty recv")
                msg = json.loads(raw)
                mid = msg.get("id")
                method = msg.get("method", "")
                if mid:
                    with self._lock:
                        self._results[mid] = msg
                        ev = self._pending.get(mid)
                    if ev:
                        ev.set()
                elif method:
                    with self._lock:
                        cb = self._callbacks.get(method)
                    if cb:
                        try:
                            cb(msg.get("params", {}))
                        except Exception as e:  # noqa: BLE001 - CDP 웹소켓 연결 헬퍼(원본) — 재연결 재시도, 이벤트 콜백 실패 무시, 종료 시 소켓 close 실패 무시 등 모두 best-effort 브라우저 자동화 인프라, 실패해도 재연결 루프로 복구됨.
                            _log.debug("CDP 이벤트 콜백 실패(무시): %s", e)
            except Exception:  # noqa: BLE001 - CDP 웹소켓 연결 헬퍼(원본) — 재연결 재시도, 이벤트 콜백 실패 무시, 종료 시 소켓 close 실패 무시 등 모두 best-effort 브라우저 자동화 인프라.
                if self._alive:
                    self._reconnect()  # 끊기면 재연결 후 계속

    def send(self, method: str, params: dict | None = None, timeout: int = 15) -> dict:
        with self._lock:
            self._seq += 1
            mid = self._seq
            ev = threading.Event()
            self._pending[mid] = ev
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        ev.wait(timeout)
        with self._lock:
            self._pending.pop(mid, None)
            return self._results.pop(mid, {})

    def js(self, expr: str, timeout: int = 8) -> str:
        r = self.send("Runtime.evaluate", {"expression": expr, "timeout": timeout * 1000}, timeout + 2)
        res = r.get("result", {}).get("result", {})
        return res.get("value", res.get("description", ""))

    def navigate(self, url: str, wait: float = 3.0):
        self.send("Page.navigate", {"url": url})
        time.sleep(wait)

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

    def dom_enable(self):
        self.send("DOM.enable")
        time.sleep(0.3)

    def query_node_ids(self, selector: str) -> list[int]:
        doc = self.send("DOM.getDocument", {"depth": 0})
        root = doc.get("result", {}).get("root", {}).get("nodeId", 0)
        if not root:
            return []
        q = self.send("DOM.querySelectorAll", {"nodeId": root, "selector": selector})
        return q.get("result", {}).get("nodeIds", [])

    def set_file_input(self, node_id: int, files: list[str]) -> dict:
        return self.send("DOM.setFileInputFiles", {"files": files, "nodeId": node_id})

    def close(self):
        self._alive = False
        try:
            self._ws.close()
        except Exception as e:  # noqa: BLE001 - CDP 웹소켓 연결 헬퍼(원본) — 재연결 재시도, 이벤트 콜백 실패 무시, 종료 시 소켓 close 실패 무시 등 모두 best-effort 브라우저 자동화 인프라, 실패해도 재연결 루프로 복구됨.
            _log.debug("CDP 종료 중 예외(무시): %s", e)
