"""ORCHESTRATOR_LOGIN_FLOW_LIVE_CHECK_FIX_AND_RETRY_01 — Naver 로그인 라이브 검증.

본 스크립트는 /ws/ui 경로로 connect 하여:
  1. browser_start 호출 → clean-start 탭 dedup 확인 (about:blank 1개)
  2. tab_list 호출 → count = 1 확인
  3. browser_action(navigate, https://www.naver.com/)
  4. login_state_change / login_action_started / login_target_selected /
     logged_in_detected / command_auto_resumed 이벤트 수집

사용:
    python -m scripts.ops.live_check_login_flow_20260520

본 모듈은 운영 데이터 변경 없음. 단순 read-only + WS 호출.
"""
from __future__ import annotations

import asyncio
import json
import time

import websockets

WS_URL = "ws://127.0.0.1:8765/ws/ui"
NAVER_LOGIN_URL = "https://www.naver.com/"

CAPTURED_TYPES = {
    "browser_start_result", "browser_status",
    "tab_list", "tab_added", "tab_removed", "tab_updated",
    "browser_action_result",
    "login_state_change", "login_action_started", "login_target_selected",
    "logged_in_detected", "command_auto_resumed",
    "popup_detected", "popup_closed", "system", "error",
}


async def _recv_until(ws, types: set[str], timeout: float) -> list[dict]:
    """timeout 까지 events 수집. types 가 비어있지 않으면 그 중 하나가 오면 즉시 반환."""
    out: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            remaining = max(0.1, deadline - time.time())
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        out.append(ev)
        et = ev.get("type", "")
        if types and et in types:
            return out
    return out


async def main() -> None:
    print(f"[connect] {WS_URL}")
    async with websockets.connect(WS_URL, max_size=4 * 1024 * 1024) as ws:
        # ── 1) browser_start
        print("[1] browser_start ...")
        await ws.send(json.dumps({"action": "browser_start"}))
        evs = await _recv_until(ws, {"browser_start_result"}, timeout=15)
        for e in evs:
            if e.get("type") in CAPTURED_TYPES:
                print("  <-", json.dumps(e, ensure_ascii=False)[:300])

        # 짧게 더 빨아들임 (broadcast 류)
        evs2 = await _recv_until(ws, set(), timeout=1.5)
        for e in evs2:
            if e.get("type") in CAPTURED_TYPES:
                print("  <-", json.dumps(e, ensure_ascii=False)[:300])

        # ── 2) tab_list
        print("[2] tab_list ...")
        await ws.send(json.dumps({"action": "tab_list"}))
        evs = await _recv_until(ws, {"tab_list"}, timeout=5)
        tab_list_payload = None
        for e in evs:
            if e.get("type") == "tab_list":
                tab_list_payload = e
            print("  <-", json.dumps(e, ensure_ascii=False)[:300])
        if tab_list_payload is not None:
            tabs = tab_list_payload.get("tabs") or tab_list_payload.get("items") or []
            print(f"[2] tab_count = {len(tabs)}")
            for t in tabs:
                print(f"    - id={t.get('id') or t.get('target_id')} url={t.get('url')} title={t.get('title')}")

        # ── 3) login_watcher_start (이미 attach 경로에서 자동 시작되지만 안전)
        await ws.send(json.dumps({"action": "login_watcher_start"}))
        await _recv_until(ws, {"login_watcher_started"}, timeout=3)

        # ── 4) navigate to Naver login
        print(f"[3] browser_action navigate → {NAVER_LOGIN_URL}")
        cmd_id = f"live-nav-{int(time.time())}"
        await ws.send(json.dumps({
            "action": "browser_action",
            "command_id": cmd_id,
            "action_type": "navigate",
            "target_id": "",
            "params": {"url": NAVER_LOGIN_URL},
        }))
        evs = await _recv_until(ws, {"browser_action_result"}, timeout=20)
        for e in evs:
            print("  <-", json.dumps(e, ensure_ascii=False)[:400])

        # ── 5) login 이벤트 수집 (사용자 직접 로그인 대기 — 최대 180초)
        print("[4] login_state 변화 수집 (사용자가 브라우저에서 로그인 진행)")
        wanted = {"logged_in_detected", "command_auto_resumed"}
        evs = await _recv_until(ws, wanted, timeout=180)
        for e in evs:
            if e.get("type") in CAPTURED_TYPES:
                print("  <-", json.dumps(e, ensure_ascii=False)[:400])

        # ── 6) tab_list 재확인
        print("[5] tab_list (최종)")
        await ws.send(json.dumps({"action": "tab_list"}))
        evs = await _recv_until(ws, {"tab_list"}, timeout=5)
        for e in evs:
            print("  <-", json.dumps(e, ensure_ascii=False)[:300])


if __name__ == "__main__":
    asyncio.run(main())
