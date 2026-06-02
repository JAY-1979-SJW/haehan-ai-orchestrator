"""브라우저 lifecycle HTTP/WS 핸들러 + CDP 유틸."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from . import browser_runtime_boundary
from ._broadcast import broadcast

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ── CDP 유틸 ──────────────────────────────────────────────────────────────────


def _fetch_cdp_targets_sync(port: int) -> list[dict]:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/json/list", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8") or "[]")
    except Exception:
        return []
    return [t for t in data if isinstance(t, dict) and t.get("type") == "page"]


async def fetch_cdp_targets(port: int) -> list[dict]:
    return await asyncio.to_thread(_fetch_cdp_targets_sync, port)


def sync_store_with_targets(targets: list[dict]) -> dict[str, list[str]]:
    _bs = browser_runtime_boundary.browser_session_store()
    ids = [str(t.get("id", "")) for t in targets if t.get("id")]
    diff = _bs.diff_targets(ids)
    for t in targets:
        tid = str(t.get("id", ""))
        if not tid:
            continue
        _bs.upsert_tab(tid, url=str(t.get("url", "")), title=str(t.get("title", "")), opened_by="cdp")
    for closed_id in diff["removed"]:
        _bs.mark_tab_closed(closed_id)
    return diff


# ── stale 탭 정리 ─────────────────────────────────────────────────────────────


def plan_stale_tab_cleanup(targets: list[dict], *, keep_url: str = "about:blank") -> dict:
    pages = [t for t in (targets or []) if isinstance(t, dict) and t.get("type") == "page"]
    if not pages:
        return {"close_ids": [], "keep_id": "", "navigate_keep_to": keep_url, "open_new_keep_url": True}
    keep = pages[0]
    close_ids = [str(t.get("id", "")) for t in pages[1:] if t.get("id")]
    keep_url_cur = str(keep.get("url", "") or "")
    return {
        "close_ids": close_ids,
        "keep_id": str(keep.get("id", "") or ""),
        "navigate_keep_to": "" if keep_url_cur == keep_url else keep_url,
        "open_new_keep_url": False,
    }


def apply_stale_tab_cleanup(targets: list[dict], cdp_port: int) -> dict:
    plan = plan_stale_tab_cleanup(targets, keep_url="about:blank")
    closed: list[str] = []
    detected = len(plan["close_ids"]) + (1 if plan["navigate_keep_to"] else 0) + (1 if plan["open_new_keep_url"] else 0)

    if plan["close_ids"]:
        try:
            from scripts.browser_tab_monitor import _close_target

            for tid in plan["close_ids"]:
                try:
                    if _close_target(tid):
                        closed.append(tid)
                except Exception:  # noqa: S112
                    continue
        except Exception:  # noqa: S110
            pass

    if plan["navigate_keep_to"]:
        try:
            from scripts.web_connector import get_page

            get_page().goto(plan["navigate_keep_to"], timeout=10000)
        except Exception:  # noqa: S110
            pass

    if plan["open_new_keep_url"]:
        try:
            from scripts.web_connector import open_page

            page = open_page()
            try:
                page.goto("about:blank", timeout=10000)
            except Exception:  # noqa: S110
                pass
        except Exception:  # noqa: S110
            pass

    return {"closed": closed, "detected": detected, "plan": plan}


def _start_via_web_connector() -> None:
    from scripts.web_connector import _ensure_cdp_daemon

    _ensure_cdp_daemon()


# ── WS 핸들러 ─────────────────────────────────────────────────────────────────


async def handle_screenshot(ws: WebSocket) -> None:
    import json as _json
    import urllib.request

    try:
        paths = browser_runtime_boundary.resolve_paths()
        cdp_port = paths.cdp_port

        def _fetch() -> list[dict]:
            url = f"http://127.0.0.1:{cdp_port}/json"
            with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310
                return _json.loads(r.read())

        targets = await asyncio.to_thread(_fetch)
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            raise RuntimeError("활성 탭 없음 — 브라우저가 실행 중인지 확인하세요.")

        import websockets  # type: ignore

        ws_debug_url: str = page["webSocketDebuggerUrl"]

        async def _capture() -> str:
            async with websockets.connect(ws_debug_url, open_timeout=5) as cdp_ws:
                cmd = _json.dumps(
                    {"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png", "quality": 80}}
                )
                await cdp_ws.send(cmd)
                raw = await asyncio.wait_for(cdp_ws.recv(), timeout=10)
                resp = _json.loads(raw)
                if "error" in resp:
                    raise RuntimeError(resp["error"].get("message", "CDP error"))
                return resp["result"]["data"]

        b64data = await _capture()
        await ws.send_json({"type": "screenshot_result", "ok": True, "format": "png", "data": b64data})
    except Exception as exc:
        await ws.send_json({"type": "screenshot_result", "ok": False, "error": str(exc)})


async def handle_browser_status(ws: WebSocket) -> None:
    from .login_watcher import start_login_watcher  # noqa: F401 — 순환 방지

    _bs = browser_runtime_boundary.browser_session_store()
    paths = browser_runtime_boundary.resolve_paths()
    decision = await asyncio.to_thread(browser_runtime_boundary.decide_browser_start, paths)
    targets = await fetch_cdp_targets(paths.cdp_port) if decision.cdp_alive else []
    if decision.cdp_alive:
        sync_store_with_targets(targets)
    await ws.send_json(
        {
            "type": "browser_status",
            "action": decision.action,
            "count": decision.count,
            "cdp_alive": decision.cdp_alive,
            "lock_active": decision.lock_active,
            "orphan_partials": decision.orphan_partials,
            "matched_pids": decision.matched_pids,
            "session": _bs.snapshot(),
            "tab_count": len(targets),
            "message_ko": decision.message_ko,
            "error": decision.error,
        }
    )


async def handle_browser_start(ws: WebSocket) -> None:
    from .login_watcher import start_login_watcher

    _bs = browser_runtime_boundary.browser_session_store()
    paths = browser_runtime_boundary.resolve_paths()
    decision = await asyncio.to_thread(browser_runtime_boundary.decide_browser_start, paths)

    if decision.action == browser_runtime_boundary.ACTION_ERROR_MULTIPLE:
        payload = {
            "type": "browser_status",
            "action": decision.action,
            "count": decision.count,
            "error": decision.error,
            "matched_pids": decision.matched_pids,
            "message_ko": decision.message_ko,
        }
        await broadcast(payload)
        await ws.send_json(
            {
                "type": "browser_start_result",
                "ok": False,
                "error": decision.error,
                "count": decision.count,
                "message_ko": decision.message_ko,
            }
        )
        return

    if decision.action == browser_runtime_boundary.ACTION_BLOCKED_BY_LOCK:
        await ws.send_json(
            {
                "type": "browser_start_result",
                "ok": False,
                "error": decision.error or "LOCK_ACTIVE",
                "message_ko": decision.message_ko,
            }
        )
        return

    if decision.action in (
        browser_runtime_boundary.ACTION_ATTACH_EXISTING,
        browser_runtime_boundary.ACTION_ATTACH_ORPHAN_CDP,
    ):
        if _bs.snapshot().get("status") != "BROWSER_RUNNING":
            _bs.start_session()
        targets = await fetch_cdp_targets(paths.cdp_port)
        sync_store_with_targets(targets)
        cleanup = await asyncio.to_thread(apply_stale_tab_cleanup, targets, paths.cdp_port)
        targets = await fetch_cdp_targets(paths.cdp_port)
        sync_store_with_targets(targets)
        await start_login_watcher()
        await ws.send_json(
            {
                "type": "browser_start_result",
                "ok": True,
                "action": decision.action,
                "count": max(decision.count, 1),
                "message_ko": decision.message_ko,
                "tab_count": len(targets),
                "stale_tabs_closed": cleanup.get("closed", []),
                "stale_tabs_detected": cleanup.get("detected", 0),
            }
        )
        return

    if decision.action == browser_runtime_boundary.ACTION_START_NEW:
        import os as _os

        browser_runtime_boundary.write_lock_file(paths, _os.getpid())
        try:
            await asyncio.to_thread(_start_via_web_connector)
            _bs.start_session()
            targets = await fetch_cdp_targets(paths.cdp_port)
            sync_store_with_targets(targets)
            ok, err, msg = True, "", "자동화 Chrome 시작 완료"
        except Exception as exc:
            ok, err, msg = False, "START_FAILED", f"자동화 Chrome 시작 실패: {exc}"
        finally:
            browser_runtime_boundary.clear_lock_file(paths)
        await ws.send_json(
            {"type": "browser_start_result", "ok": ok, "action": decision.action, "error": err, "message_ko": msg}
        )


async def handle_browser_quit(ws: WebSocket) -> None:
    from .login_watcher import stop_login_watcher

    _bs = browser_runtime_boundary.browser_session_store()
    await stop_login_watcher()
    paths = browser_runtime_boundary.resolve_paths()
    result = await asyncio.to_thread(browser_runtime_boundary.quit_automation_browsers, paths)
    _bs.mark_browser_closed()
    await broadcast(
        {
            "type": "browser_status",
            "action": "browser_quit",
            "count": 0,
            "killed_pids": result.get("killed_pids", []),
            "failed_pids": result.get("failed_pids", []),
            "ok": result.get("ok", False),
        }
    )
    await ws.send_json({"type": "browser_quit_result", **result})


async def handle_tab_list(ws: WebSocket) -> None:
    _bs = browser_runtime_boundary.browser_session_store()
    paths = browser_runtime_boundary.resolve_paths()
    targets = await fetch_cdp_targets(paths.cdp_port)
    diff = sync_store_with_targets(targets)
    await ws.send_json(
        {
            "type": "tab_list",
            "tabs": [
                {"tab_id": str(t.get("id", "")), "url": t.get("url", ""), "title": t.get("title", "")} for t in targets
            ],
            "diff": diff,
            "session": _bs.snapshot(),
        }
    )
    if diff["added"]:
        await broadcast({"type": "popup_detected", "added": diff["added"], "ts": time.time()})


async def handle_tab_close(ws: WebSocket, tab_id: str) -> None:
    import urllib.request

    _bs = browser_runtime_boundary.browser_session_store()
    TAB_CLOSED = browser_runtime_boundary.TAB_CLOSED
    tab_id = str(tab_id or "").strip()
    if not tab_id:
        await ws.send_json({"type": "tab_close_result", "ok": False, "error": "MISSING_TAB_ID"})
        return

    known = _bs.get_tab(tab_id)
    if known is not None and known.status == TAB_CLOSED:
        await ws.send_json(
            {
                "type": "tab_close_result",
                "ok": False,
                "tab_id": tab_id,
                "status": TAB_CLOSED,
                "error": "TAB_CLOSED",
                "message_ko": "이미 닫힌 탭입니다 — 새 탭을 만들지 않습니다.",
            }
        )
        return

    paths = browser_runtime_boundary.resolve_paths()

    def _close() -> bool:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{int(paths.cdp_port)}/json/close/{tab_id}", timeout=1.5
            ) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    ok = await asyncio.to_thread(_close)
    _bs.mark_tab_closed(tab_id)
    await ws.send_json({"type": "tab_close_result", "ok": ok, "tab_id": tab_id, "status": TAB_CLOSED})


# ── browser_action ────────────────────────────────────────────────────────────


async def handle_browser_action(ws: WebSocket, data: dict) -> None:
    await execute_browser_action(data, send_to=ws)


async def execute_browser_action(payload: dict, *, send_to) -> None:
    from .login_watcher import login_precheck_and_enqueue

    ERR_TARGET_CLOSED = browser_runtime_boundary.ERR_TARGET_CLOSED
    ERR_TARGET_NOT_FOUND = browser_runtime_boundary.ERR_TARGET_NOT_FOUND

    req = browser_runtime_boundary.build_browser_action_request(payload)

    if not payload.get("_from_resume"):
        if await login_precheck_and_enqueue("browser_action", payload):
            msg = {
                "type": "browser_action_status",
                "status": "waiting_login",
                "command_id": req.command_id,
                "action_type": req.action_type,
            }
            if send_to is not None:
                await send_to.send_json(msg)
            await broadcast(msg)
            return

    await broadcast(
        {
            "type": "browser_action_started",
            "command_id": req.command_id,
            "action_type": req.action_type,
            "target_id": req.target_id,
            "ts": time.time(),
        }
    )

    try:
        result = await asyncio.to_thread(browser_runtime_boundary.execute_browser_action, req)
    except Exception as exc:
        await broadcast(
            {
                "type": "browser_action_failed",
                "command_id": req.command_id,
                "action_type": req.action_type,
                "target_id": req.target_id,
                "error_code": "RUNNER_FAILED",
                "reason": f"{type(exc).__name__}: {exc}",
                "recoverable": True,
                "ts": time.time(),
            }
        )
        if send_to is not None:
            await send_to.send_json(
                {
                    "type": "browser_action_result",
                    "ok": False,
                    "command_id": req.command_id,
                    "error_code": "RUNNER_FAILED",
                }
            )
        return

    result_dict = result.to_dict()
    if result.ok:
        await broadcast({"type": "browser_action_completed", **result_dict, "ts": time.time()})
    else:
        evt_type = "browser_action_failed"
        if result.error_code == ERR_TARGET_NOT_FOUND:
            evt_type = "target_not_found"
        elif result.error_code == ERR_TARGET_CLOSED:
            evt_type = "target_closed"
        await broadcast({"type": evt_type, **result_dict, "ts": time.time()})

    if send_to is not None:
        await send_to.send_json({"type": "browser_action_result", **result_dict})
