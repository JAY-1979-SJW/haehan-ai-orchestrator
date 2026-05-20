"""로컬 데스크탑 앱 전용 FastAPI 서버 (포트 8765).

- 서버(8000)와 WebSocket으로 연결 → 태스크 Push 수신
- 로컬 UI(HTML)에 WebSocket으로 실시간 전달
- 사용자 설정 저장/로드 API 제공
- 민감 정보 절대 노출 금지
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .user_settings import load_menu, save_menu

logger = logging.getLogger(__name__)

_UI_DIR = Path(__file__).parent / "ui_dist"
_SERVER_WS_URL = "wss://api.haehan-ai.kr/ws/desktop"  # 서버 측 Push WebSocket

app = FastAPI(title="Haehan Desktop Local Server", docs_url=None, redoc_url=None)

# ── 연결된 로컬 UI 클라이언트 목록 ────────────────────────────────────────────
_ui_clients: list[WebSocket] = []


async def _broadcast(msg: dict[str, Any]) -> None:
    """연결된 모든 UI 클라이언트에 메시지 전송."""
    dead = []
    for ws in _ui_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ui_clients.remove(ws)


# ── UI ↔ 로컬서버 WebSocket ───────────────────────────────────────────────────
@app.websocket("/ws/ui")
async def ws_ui(ws: WebSocket):
    await ws.accept()
    _ui_clients.append(ws)
    logger.info("UI client connected (total=%d)", len(_ui_clients))
    try:
        while True:
            data = await ws.receive_json()
            await _handle_ui_message(data, ws)
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ui_clients:
            _ui_clients.remove(ws)
        logger.info("UI client disconnected (total=%d)", len(_ui_clients))


async def _handle_ui_message(data: dict, ws: WebSocket) -> None:
    """UI에서 온 메시지 처리."""
    action = data.get("action", "")

    if action == "load_menu":
        user_id = data.get("user_id", "default")
        role = data.get("role", "any")
        menu = load_menu(user_id, role)
        await ws.send_json({"type": "menu", "items": menu})

    elif action == "save_menu":
        user_id = data.get("user_id", "default")
        items = data.get("items", [])
        save_menu(user_id, items)
        await ws.send_json({"type": "menu_saved", "ok": True})

    elif action == "chat":
        text = data.get("text", "").strip()
        if text:
            # UI가 이미 자기 메시지를 로컬 추가했으므로 broadcast 불필요 — 서버 전달만
            await _send_to_server({"action": "chat", "text": text})

    elif action == "approve":
        task_id = data.get("task_id")
        await _send_to_server({"action": "approve", "task_id": task_id})
        await _broadcast({"type": "system", "text": f"✅ 승인 전송: {task_id}"})

    elif action == "reject":
        task_id = data.get("task_id")
        await _send_to_server({"action": "reject", "task_id": task_id})
        await _broadcast({"type": "system", "text": f"❌ 거부 전송: {task_id}"})

    elif action == "blog_write":
        asyncio.create_task(_run_blog_write(data))

    elif action == "blog_confirm":
        asyncio.create_task(_run_blog_confirm())

    elif action == "cafe_write":
        asyncio.create_task(_run_cafe_write(data))

    elif action == "cafe_confirm":
        asyncio.create_task(_run_cafe_confirm())

    elif action == "browser_status":
        await _handle_browser_status(ws)

    elif action == "browser_start":
        await _handle_browser_start(ws)

    elif action == "browser_quit":
        await _handle_browser_quit(ws)

    elif action == "tab_list":
        await _handle_tab_list(ws)

    elif action == "tab_close":
        await _handle_tab_close(ws, data.get("tab_id", ""))


# ── 브라우저 lifecycle 핸들러 ────────────────────────────────────────────────

def _fetch_cdp_targets_sync(port: int) -> list[dict]:
    """CDP /json/list — page 타입만 반환."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{int(port)}/json/list", timeout=1.5,
        ) as resp:
            data = json.loads(resp.read().decode("utf-8") or "[]")
    except Exception:
        return []
    return [t for t in data if isinstance(t, dict) and t.get("type") == "page"]


async def _fetch_cdp_targets(port: int) -> list[dict]:
    return await asyncio.to_thread(_fetch_cdp_targets_sync, port)


def _sync_store_with_targets(targets: list[dict]) -> dict[str, list[str]]:
    """현재 CDP target 목록과 session_store 의 탭을 정합."""
    from local_agent.browser_session_store import default_store as _bs

    ids = [str(t.get("id", "")) for t in targets if t.get("id")]
    diff = _bs.diff_targets(ids)
    for t in targets:
        tid = str(t.get("id", ""))
        if not tid:
            continue
        _bs.upsert_tab(
            tid,
            url=str(t.get("url", "")),
            title=str(t.get("title", "")),
            opened_by="cdp",
        )
    for closed_id in diff["removed"]:
        _bs.mark_tab_closed(closed_id)
    return diff


async def _handle_browser_status(ws: WebSocket) -> None:
    from local_agent.browser_instance_guard import decide_browser_start, resolve_paths
    from local_agent.browser_session_store import default_store as _bs

    paths = resolve_paths()
    decision = await asyncio.to_thread(decide_browser_start, paths)
    targets = await _fetch_cdp_targets(paths.cdp_port) if decision.cdp_alive else []
    if decision.cdp_alive:
        _sync_store_with_targets(targets)
    payload = {
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
    await ws.send_json(payload)


async def _handle_browser_start(ws: WebSocket) -> None:
    from local_agent.browser_instance_guard import (
        ACTION_ATTACH_EXISTING,
        ACTION_ATTACH_ORPHAN_CDP,
        ACTION_BLOCKED_BY_LOCK,
        ACTION_ERROR_MULTIPLE,
        ACTION_START_NEW,
        decide_browser_start,
        resolve_paths,
    )
    from local_agent.browser_session_store import default_store as _bs

    paths = resolve_paths()
    decision = await asyncio.to_thread(decide_browser_start, paths)

    if decision.action == ACTION_ERROR_MULTIPLE:
        await _broadcast({
            "type": "browser_status",
            "action": decision.action,
            "count": decision.count,
            "error": decision.error,
            "matched_pids": decision.matched_pids,
            "message_ko": decision.message_ko,
        })
        await ws.send_json({
            "type": "browser_start_result",
            "ok": False,
            "error": decision.error,
            "count": decision.count,
            "message_ko": decision.message_ko,
        })
        return

    if decision.action == ACTION_BLOCKED_BY_LOCK:
        await ws.send_json({
            "type": "browser_start_result",
            "ok": False,
            "error": decision.error or "LOCK_ACTIVE",
            "message_ko": decision.message_ko,
        })
        return

    if decision.action in (ACTION_ATTACH_EXISTING, ACTION_ATTACH_ORPHAN_CDP):
        _bs.start_session() if _bs.snapshot().get("status") != "BROWSER_RUNNING" else None
        targets = await _fetch_cdp_targets(paths.cdp_port)
        _sync_store_with_targets(targets)
        await ws.send_json({
            "type": "browser_start_result",
            "ok": True,
            "action": decision.action,
            "count": max(decision.count, 1),
            "message_ko": decision.message_ko,
            "tab_count": len(targets),
        })
        return

    # ACTION_START_NEW → 실제 시작은 기존 web_connector._ensure_cdp_daemon 경로에 위임.
    # 이번 공정에서는 데몬을 직접 spawn 하지 않고 안내만 한다.
    if decision.action == ACTION_START_NEW:
        from local_agent.browser_instance_guard import write_lock_file
        import os as _os

        write_lock_file(paths, _os.getpid())
        try:
            await asyncio.to_thread(_start_via_web_connector)
            _bs.start_session()
            targets = await _fetch_cdp_targets(paths.cdp_port)
            _sync_store_with_targets(targets)
            ok = True
            err = ""
            msg = "자동화 Chrome 시작 완료"
        except Exception as exc:
            ok = False
            err = "START_FAILED"
            msg = f"자동화 Chrome 시작 실패: {exc}"
        finally:
            from local_agent.browser_instance_guard import clear_lock_file
            clear_lock_file(paths)
        await ws.send_json({
            "type": "browser_start_result",
            "ok": ok,
            "action": decision.action,
            "error": err,
            "message_ko": msg,
        })


def _start_via_web_connector() -> None:
    """기존 web_connector 경로를 통해 데몬 자동 기동."""
    from scripts.web_connector import _ensure_cdp_daemon  # noqa: WPS437 — 의도된 내부 사용

    _ensure_cdp_daemon()


async def _handle_browser_quit(ws: WebSocket) -> None:
    from local_agent.browser_instance_guard import (
        quit_automation_browsers,
        resolve_paths,
    )
    from local_agent.browser_session_store import default_store as _bs

    paths = resolve_paths()
    result = await asyncio.to_thread(quit_automation_browsers, paths)
    _bs.mark_browser_closed()
    await _broadcast({
        "type": "browser_status",
        "action": "browser_quit",
        "count": 0,
        "killed_pids": result.get("killed_pids", []),
        "failed_pids": result.get("failed_pids", []),
        "ok": result.get("ok", False),
    })
    await ws.send_json({
        "type": "browser_quit_result",
        **result,
    })


async def _handle_tab_list(ws: WebSocket) -> None:
    from local_agent.browser_instance_guard import resolve_paths
    from local_agent.browser_session_store import default_store as _bs

    paths = resolve_paths()
    targets = await _fetch_cdp_targets(paths.cdp_port)
    diff = _sync_store_with_targets(targets)
    await ws.send_json({
        "type": "tab_list",
        "tabs": [
            {
                "tab_id": str(t.get("id", "")),
                "url": t.get("url", ""),
                "title": t.get("title", ""),
            }
            for t in targets
        ],
        "diff": diff,
        "session": _bs.snapshot(),
    })
    if diff["added"]:
        await _broadcast({
            "type": "popup_detected",
            "added": diff["added"],
            "ts": time.time(),
        })


async def _handle_tab_close(ws: WebSocket, tab_id: str) -> None:
    from local_agent.browser_instance_guard import resolve_paths
    from local_agent.browser_session_store import (
        TAB_CLOSED,
        default_store as _bs,
    )
    import urllib.request

    tab_id = str(tab_id or "").strip()
    if not tab_id:
        await ws.send_json({
            "type": "tab_close_result", "ok": False, "error": "MISSING_TAB_ID",
        })
        return

    known = _bs.get_tab(tab_id)
    if known is not None and known.status == TAB_CLOSED:
        await ws.send_json({
            "type": "tab_close_result",
            "ok": False,
            "tab_id": tab_id,
            "status": TAB_CLOSED,
            "error": "TAB_CLOSED",
            "message_ko": "이미 닫힌 탭입니다 — 새 탭을 만들지 않습니다.",
        })
        return

    paths = resolve_paths()

    def _close() -> bool:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{int(paths.cdp_port)}/json/close/{tab_id}",
                timeout=1.5,
            ) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    ok = await asyncio.to_thread(_close)
    _bs.mark_tab_closed(tab_id)
    await ws.send_json({
        "type": "tab_close_result",
        "ok": ok,
        "tab_id": tab_id,
        "status": TAB_CLOSED,
    })


# ── 블로그 작성 — 스레드에서 blocking I/O 실행 ────────────────────────────────
async def _run_blog_write(data: dict) -> None:
    """write_post()를 스레드풀에서 실행하고 상태를 UI에 브로드캐스트."""
    title      = data.get("title", "").strip()
    body       = data.get("body", "").strip()
    visibility = data.get("visibility", "public")
    brand_tags = data.get("brand_tags") or []

    if not title or not body:
        await _broadcast({"type": "blog_status", "status": "error", "error": "제목과 본문은 필수입니다."})
        return

    await _broadcast({"type": "blog_status", "status": "writing", "title": title})

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _blog_write_sync, title, body, visibility, brand_tags)
    except Exception as exc:
        logger.error("blog_write error: %s", exc)
        await _broadcast({"type": "blog_status", "status": "error", "error": str(exc)})
        return

    if result.get("mode") == "awaiting_approval":
        s = result.get("summary", {})
        await _broadcast({
            "type": "blog_status",
            "status": "awaiting_approval",
            "title": s.get("title", title),
            "tags": s.get("tags", []),
            "visibility": s.get("visibility", visibility),
            "body_preview": s.get("body_preview", ""),
        })
    else:
        await _broadcast({
            "type": "blog_status",
            "status": "error",
            "error": result.get("error", "작성 실패"),
        })


def _blog_write_sync(title: str, body: str, visibility: str, brand_tags: list) -> dict:
    from scripts.web_connector import get_page
    from scripts.naver.blog.writer import write_post
    page = get_page()
    return write_post(
        page,
        title=title,
        body=body,
        visibility=visibility,
        brand_tags=brand_tags or None,
        require_approval=True,
    )


async def _run_blog_confirm() -> None:
    """발행 패널이 열린 상태에서 confirm_publish()를 스레드풀에서 실행."""
    await _broadcast({"type": "blog_status", "status": "confirming"})
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _blog_confirm_sync)
    except Exception as exc:
        logger.error("blog_confirm error: %s", exc)
        await _broadcast({"type": "blog_status", "status": "error", "error": str(exc)})
        return

    if result.get("ok"):
        await _broadcast({
            "type": "blog_status",
            "status": "done",
            "result_url": result.get("url", ""),
        })
    else:
        await _broadcast({
            "type": "blog_status",
            "status": "error",
            "error": result.get("error", "발행 실패"),
        })


def _blog_confirm_sync() -> dict:
    from scripts.web_connector import get_page
    from scripts.naver.blog.writer import confirm_publish
    page = get_page()
    return confirm_publish(page)


# ── 카페 글쓰기 ───────────────────────────────────────────────────────────────
async def _run_cafe_write(data: dict) -> None:
    cafe_url   = data.get("cafe_url", "https://cafe.naver.com/0moo")
    board      = data.get("board", "")
    title      = data.get("title", "").strip()
    body       = data.get("body", "").strip()
    tags       = data.get("tags") or []
    members_only = data.get("members_only", False)

    if not title or not body:
        await _broadcast({"type": "cafe_status", "status": "error", "error": "제목과 본문은 필수입니다."})
        return

    await _broadcast({"type": "cafe_status", "status": "writing", "title": title, "board": board})

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, _cafe_write_sync, cafe_url, board, title, body, tags, members_only
        )
    except Exception as exc:
        logger.error("cafe_write error: %s", exc)
        await _broadcast({"type": "cafe_status", "status": "error", "error": str(exc)})
        return

    if result.get("mode") == "awaiting_approval":
        s = result.get("summary", {})
        await _broadcast({
            "type": "cafe_status",
            "status": "awaiting_approval",
            "title": s.get("title", title),
            "board": s.get("board", board),
            "body_preview": s.get("body_preview", ""),
        })
    else:
        await _broadcast({
            "type": "cafe_status",
            "status": "error",
            "error": result.get("error", "작성 실패"),
        })


def _cafe_write_sync(cafe_url: str, board: str, title: str, body: str,
                     tags: list, members_only: bool) -> dict:
    from scripts.web_connector import get_page
    from scripts.naver.cafe.writer import write_post
    page = get_page()
    return write_post(
        page,
        cafe_url=cafe_url,
        board_name=board,
        title=title,
        body=body,
        tags=tags or None,
        members_only=members_only,
        require_approval=True,
    )


async def _run_cafe_confirm() -> None:
    await _broadcast({"type": "cafe_status", "status": "confirming"})
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _cafe_confirm_sync)
    except Exception as exc:
        logger.error("cafe_confirm error: %s", exc)
        await _broadcast({"type": "cafe_status", "status": "error", "error": str(exc)})
        return

    if result.get("ok"):
        await _broadcast({
            "type": "cafe_status",
            "status": "done",
            "result_url": result.get("url", ""),
        })
    else:
        await _broadcast({
            "type": "cafe_status",
            "status": "error",
            "error": result.get("error", "발행 실패"),
        })


def _cafe_confirm_sync() -> dict:
    from scripts.web_connector import get_page
    from scripts.naver.cafe.writer import confirm_publish
    page = get_page()
    return confirm_publish(page)


# ── 서버(8000) WebSocket 연결 및 Push 수신 ────────────────────────────────────
_server_ws: Any = None


async def _send_to_server(msg: dict) -> None:
    global _server_ws
    if _server_ws:
        try:
            await _server_ws.send(json.dumps(msg))
        except Exception as exc:
            logger.warning("server ws send error: %s", exc)


async def _connect_to_server() -> None:
    """서버 WebSocket에 연결 — 재연결 루프."""
    global _server_ws
    import websockets  # type: ignore

    while True:
        try:
            async with websockets.connect(_SERVER_WS_URL) as ws:
                _server_ws = ws
                await _broadcast({"type": "system", "text": "🟢 서버 연결됨"})
                logger.info("connected to server WebSocket")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        await _on_server_message(msg)
                    except Exception as exc:
                        logger.warning("server message parse error: %s", exc)
        except Exception as exc:
            _server_ws = None
            await _broadcast({"type": "system", "text": f"🔴 서버 연결 끊김 — 재연결 중…"})
            logger.warning("server ws disconnected: %s — retry in 5s", exc)
            await asyncio.sleep(5)


async def _on_server_message(msg: dict) -> None:
    """서버에서 온 메시지를 UI로 전달."""
    msg_type = msg.get("type", "")

    if msg_type == "task":
        await _broadcast({
            "type": "task",
            "task_id": msg.get("task_id"),
            "action_type": msg.get("action_type", ""),
            "domain": msg.get("domain", ""),
            "risk_level": msg.get("risk_level", "low"),
            "description": msg.get("description", ""),
            "needs_approval": msg.get("needs_approval", False),
            "execution_location": msg.get("execution_location", ""),
            "status": msg.get("status", "수신 대기"),
            "ts": time.time(),
        })
    elif msg_type == "user_present_task":
        # UI 미연결 상태에서는 실행을 보류한다. WAITING_USER_PRESENT 유지.
        task = msg.get("task") or {}
        if not _ui_clients:
            workflow_run_id = task.get("workflow_run_id", "")
            await _send_to_server({
                "action": "user_present_ack",
                "workflow_run_id": workflow_run_id,
                "status": "WAITING_FOR_USER",
                "ui_connected": False,
            })
            logger.info(
                "user_present_task held: UI disconnected (workflow_run_id=%s)",
                workflow_run_id,
            )
            return
        await _broadcast({"type": "user_present_task", "task": task, "ts": time.time()})
    elif msg_type == "task_blocked":
        # 서버측 정책 차단 통지 — UI에 사유만 표시. 실행 명령 아님.
        await _broadcast({
            "type": "task_blocked",
            "task_id": msg.get("task_id", ""),
            "workflow_run_id": msg.get("workflow_run_id", ""),
            "reason": msg.get("reason", ""),
            "message_ko": msg.get("message_ko", ""),
            "ts": time.time(),
        })
    elif msg_type == "result":
        await _broadcast({
            "type": "chat",
            "role": "assistant",
            "text": msg.get("message", "작업 완료"),
            "ts": time.time(),
        })
    elif msg_type == "browser_status":
        await _broadcast({"type": "browser_status", **msg})
    else:
        await _broadcast(msg)


_AUTOWORK_BASE = "https://autowork.haehan-ai.kr"
_PROXY_STRIP_HEADERS = {"x-frame-options", "content-security-policy", "content-encoding", "transfer-encoding"}

@app.get("/proxy/admin/{path:path}")
async def proxy_admin(path: str, request: Request) -> Response:
    """autowork.haehan-ai.kr 페이지를 프록시로 서빙 — X-Frame-Options 제거."""
    target = f"{_AUTOWORK_BASE}/{path}"
    params = str(request.url.query)
    if params:
        target += f"?{params}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(target, headers={"Accept": "text/html,application/xhtml+xml,*/*"})
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in _PROXY_STRIP_HEADERS}
        return Response(content=resp.content, status_code=resp.status_code,
                        headers=headers, media_type=resp.headers.get("content-type"))
    except Exception as exc:
        logger.warning("proxy error %s: %s", target, exc)
        return Response(content=f"프록시 오류: {exc}".encode(), status_code=502)


_LOG_FILE = Path(__file__).parent.parent / "data" / "logs" / "app.log"
_LOG_MAX_LINES = 500


@app.get("/logs")
async def get_logs():
    """최근 로그 라인 반환."""
    try:
        if not _LOG_FILE.exists():
            return {"lines": [], "error": "로그 파일 없음"}
        text = _LOG_FILE.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()[-_LOG_MAX_LINES:]
        return {"lines": lines}
    except Exception as exc:
        logger.warning("logs read error: %s", exc)
        return {"lines": [], "error": str(exc)}


@app.on_event("startup")
async def startup():
    asyncio.create_task(_connect_to_server())
    logger.info("local server started on port 8765")


# ── 정적 파일 서빙 — 모든 API/WS 라우트 등록 후 마지막에 마운트 ────────────────
# index.html 이 /assets/... 경로로 JS/CSS 요청하므로 루트("/")에 마운트해야 함
app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


def run():
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
