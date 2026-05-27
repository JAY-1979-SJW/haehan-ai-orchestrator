"""CDP 헬퍼 (mail_read 전용) — 외부 의존 최소화.

자동화 Chrome 9222 fixed. WebSocket 한 호출당 fresh 연결.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import websocket  # type: ignore

CDP_PORT = 9222


def list_pages(port: int = CDP_PORT) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2.0) as r:
        rows = json.loads(r.read() or b"[]")
    return [t for t in rows if t.get("type") == "page"]


def find_target(predicate, port: int = CDP_PORT) -> dict | None:
    for t in list_pages(port):
        if predicate(t):
            return t
    return None


def _send(ws, msg_id: int, method: str, params: dict | None = None,
          timeout: float = 8.0) -> dict:
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            raw = ws.recv()
        except Exception:
            return {"id": msg_id, "_timeout": True}
        try:
            m = json.loads(raw)
        except Exception:
            continue
        if m.get("id") == msg_id:
            return m
    return {"id": msg_id, "_timeout": True}


def evaluate(target_id: str, expr: str, timeout: float = 8.0, port: int = CDP_PORT) -> Any:
    for t in list_pages(port):
        if t.get("id") == target_id:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=8)
            ev = _send(ws, 1, "Runtime.evaluate",
                       {"expression": expr, "returnByValue": True}, timeout=timeout)
            ws.close()
            val = ev.get("result", {}).get("result", {}).get("value")
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return val
            return val
    return None


def navigate(target_id: str, url: str, port: int = CDP_PORT) -> None:
    for t in list_pages(port):
        if t.get("id") == target_id:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
            _send(ws, 10, "Page.navigate", {"url": url}, timeout=5.0)
            ws.close()
            return


def create_target(url: str = "about:blank", port: int = CDP_PORT) -> str:
    """Create a new tab in an existing CDP browser session.

    This does not launch, restart, or close the browser. It only asks the
    already-running CDP endpoint to create an isolated target for concurrent
    automation work.
    """
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
        browser_ws = json.loads(r.read())["webSocketDebuggerUrl"]
    ws = websocket.create_connection(browser_ws, timeout=8)
    try:
        ev = _send(ws, 1, "Target.createTarget", {"url": url}, timeout=5.0)
    finally:
        ws.close()
    return str(ev.get("result", {}).get("targetId") or "")


def screenshot_png(target_id: str, port: int = CDP_PORT) -> bytes | None:
    for t in list_pages(port):
        if t.get("id") == target_id:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=8)
            ev = _send(ws, 2, "Page.captureScreenshot", {"format": "png"}, timeout=10.0)
            ws.close()
            import base64
            data = ev.get("result", {}).get("data")
            return base64.b64decode(data) if data else None
    return None


def ensure_about_blank_target(port: int = CDP_PORT) -> str:
    """about:blank 또는 mail.naver.com 탭 우선 반환. 없으면 신규 생성."""
    for t in list_pages(port):
        if "mail.naver" in t.get("url", ""):
            return t["id"]
    for t in list_pages(port):
        if t.get("url") in ("about:blank", "chrome://newtab/"):
            return t["id"]
    # 새 탭 생성
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
        browser_ws = json.loads(r.read())["webSocketDebuggerUrl"]
    ws = websocket.create_connection(browser_ws, timeout=8)
    ev = _send(ws, 1, "Target.createTarget", {"url": "about:blank"}, timeout=5.0)
    ws.close()
    return ev.get("result", {}).get("targetId", "")


def wait_dom(target_id: str, expr_truthy: str, timeout: float = 18.0,
             interval: float = 1.0, port: int = CDP_PORT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = evaluate(target_id, f"!!({expr_truthy})", timeout=4.0, port=port)
        if v is True:
            return True
        time.sleep(interval)
    return False
