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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import agent_runtime_boundary, browser_runtime_boundary
from .user_settings import load_menu, save_menu
from .remote_access import is_enabled as _remote_enabled, verify_token as _verify_token

logger = logging.getLogger(__name__)


# ── 원격 접속 토큰 미들웨어 ──────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

_EXEMPT_PATHS = {"/ws/ui", "/health"}


class RemoteAccessMiddleware(BaseHTTPMiddleware):
    """비 localhost 요청에 Bearer 토큰 검증. 원격 접속 비활성 시 localhost만 허용."""

    async def dispatch(self, request: StarletteRequest, call_next):
        # BaseHTTPMiddleware는 WebSocket 업그레이드 요청에서 request.client가 None이 되는
        # Starlette 버그가 있으므로, WS 경로는 scope에서 직접 host를 읽음
        if request.scope.get("type") == "websocket":
            client_host = (request.scope.get("client") or ["127.0.0.1"])[0]
        else:
            client_host = (request.client.host if request.client else "") or ""
        is_local = client_host in ("127.0.0.1", "::1", "localhost")
        if is_local:
            return await call_next(request)
        # 비 localhost — 원격 접속 활성 여부 확인
        if not _remote_enabled():
            return StarletteResponse("원격 접속이 비활성화되어 있습니다.", status_code=403)
        # WebSocket 업그레이드는 Sec-WebSocket-Protocol 또는 쿼리로 토큰 전달
        if request.url.path in _EXEMPT_PATHS or request.url.path.startswith("/ws/"):
            token = request.query_params.get("token", "")
        else:
            auth = request.headers.get("Authorization", "")
            token = auth.removeprefix("Bearer ").strip()
        if not _verify_token(token):
            return StarletteResponse("액세스 토큰 불일치", status_code=401)
        return await call_next(request)


def _resolve_ui_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        # onedir: exe 옆 _internal/ 폴더가 sys._MEIPASS
        # onefile: sys._MEIPASS 임시 디렉터리
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
        for candidate in (
            base / "desktop" / "ui_dist",
            base / "ui_dist",
            Path(sys.executable).parent / "_internal" / "desktop" / "ui_dist",
            Path(sys.executable).parent / "_internal" / "ui_dist",
        ):
            if (candidate / "index.html").exists():
                return candidate
    return Path(__file__).parent / "ui_dist"

_UI_DIR = _resolve_ui_dir()
_SERVER_WS_URL = "wss://api.haehan-ai.kr/ws/desktop"  # 서버 측 Push WebSocket

@asynccontextmanager
async def lifespan(app: FastAPI):
    server_task = asyncio.create_task(_connect_to_server())
    from desktop.app_config import LOCAL_HOST, LOCAL_PORT
    logger.info("local server started on %s:%s", LOCAL_HOST, LOCAL_PORT)
    try:
        yield
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("server websocket task shutdown error: %s", type(exc).__name__)


app = FastAPI(title="Haehan Desktop Local Server", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(RemoteAccessMiddleware)


# ── 전역 예외 핸들러 — 보안 마스킹 ─────────────────────────────────────────────
# HTTPException / RequestValidationError / 인증 오류: 기존 status_code 유지
# 예상 밖 Exception만 500으로 마스킹 (stack trace / secret / token 노출 금지)

@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def _generic_exception_handler(request: Request, exc: Exception):
    logger.error("처리되지 않은 예외 [%s %s]: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "내부 서버 오류"})


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

    elif action == "naver_cafe_list":
        asyncio.create_task(_run_naver_cafe_list(ws))

    elif action == "naver_cafe_posts":
        asyncio.create_task(_run_naver_cafe_posts(ws, data))

    elif action == "naver_cafe_read":
        asyncio.create_task(_run_naver_cafe_read(ws, data))

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

    elif action == "login_watcher_start":
        await _start_login_watcher()
        await ws.send_json({"type": "login_watcher_started", "ok": True})

    elif action == "login_watcher_stop":
        await _stop_login_watcher()
        await ws.send_json({"type": "login_watcher_stopped", "ok": True})

    elif action == "browser_action":
        await _handle_browser_action(ws, data)

    elif action == "screenshot":
        await _handle_screenshot(ws)


# ── 스크린샷 ──────────────────────────────────────────────────────────────────
async def _handle_screenshot(ws: WebSocket) -> None:
    """CDP /json API로 첫 번째 활성 탭을 찾아 Page.captureScreenshot 호출."""
    import base64
    import json as _json
    import urllib.request

    try:
        paths = browser_runtime_boundary.resolve_paths()
        cdp_port = paths.cdp_port

        # 탭 목록 조회
        def _fetch_targets() -> list[dict]:
            url = f"http://127.0.0.1:{cdp_port}/json"
            with urllib.request.urlopen(url, timeout=3) as r:
                return _json.loads(r.read())

        targets = await asyncio.to_thread(_fetch_targets)
        # page 타입 중 첫 번째 선택
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            raise RuntimeError("활성 탭 없음 — 브라우저가 실행 중인지 확인하세요.")

        ws_debug_url: str = page["webSocketDebuggerUrl"]

        # aiohttp 없이 asyncio WebSocket으로 CDP 명령 전송
        import websockets  # type: ignore

        async def _capture() -> str:
            async with websockets.connect(ws_debug_url, open_timeout=5) as cdp_ws:
                cmd = _json.dumps({"id": 1, "method": "Page.captureScreenshot",
                                   "params": {"format": "png", "quality": 80}})
                await cdp_ws.send(cmd)
                raw = await asyncio.wait_for(cdp_ws.recv(), timeout=10)
                resp = _json.loads(raw)
                if "error" in resp:
                    raise RuntimeError(resp["error"].get("message", "CDP error"))
                return resp["result"]["data"]

        b64data = await _capture()
        await ws.send_json({
            "type": "screenshot_result",
            "ok": True,
            "format": "png",
            "data": b64data,
        })
    except Exception as exc:
        await ws.send_json({
            "type": "screenshot_result",
            "ok": False,
            "error": str(exc),
        })


# ── 로그인 watcher (background poller) ───────────────────────────────────────

_login_watcher_task: asyncio.Task | None = None
_login_watcher_state = {
    "prev_targets": [],         # list[TargetSnapshot]
    "prev_login_states": {},    # target_id → state
    "engine": None,             # LoginAutoFlowEngine
}
_LOGIN_WATCHER_INTERVAL_SEC = 2.0


async def _start_login_watcher() -> None:
    global _login_watcher_task
    if _login_watcher_task is not None and not _login_watcher_task.done():
        return
    _ensure_engine()
    _login_watcher_task = asyncio.create_task(_login_watcher_loop())


async def _stop_login_watcher() -> None:
    global _login_watcher_task
    if _login_watcher_task is None:
        return
    _login_watcher_task.cancel()
    try:
        await _login_watcher_task
    except (asyncio.CancelledError, Exception):
        pass
    _login_watcher_task = None


async def _login_watcher_loop() -> None:
    paths = browser_runtime_boundary.resolve_paths()
    _bs = browser_runtime_boundary.browser_session_store()
    while True:
        try:
            rows = await _fetch_cdp_targets(paths.cdp_port)
            curr = browser_runtime_boundary.from_cdp_targets(rows)
            prev = _login_watcher_state["prev_targets"]
            evs = browser_runtime_boundary.compute_events(prev, curr)
            for e in evs:
                await _broadcast({
                    "type": e.event_type,
                    "target_id": e.target_id,
                    "sanitized_url": e.sanitized_url,
                    "title": e.title,
                    "extra": e.extra,
                    "ts": time.time(),
                })
            login_states = browser_runtime_boundary.detect_login_states(
                curr, prev_states=_login_watcher_state["prev_login_states"],
            )
            login_evs = browser_runtime_boundary.login_state_change_events(
                _login_watcher_state["prev_login_states"], login_states,
            )
            engine = _login_watcher_state["engine"]
            for ev in login_evs:
                await _broadcast({
                    "type": ev.event_type,
                    "target_id": ev.target_id,
                    "sanitized_url": ev.sanitized_url,
                    "title": ev.title,
                    "extra": ev.extra,
                    "ts": time.time(),
                })
                det = login_states.get(ev.target_id)
                if det is None:
                    continue
                _bs.set_login_state(ev.target_id, det.state)
                for engine_ev in engine.on_target_state(ev.target_id, det):
                    await _broadcast({
                        "type": engine_ev.type,
                        "target_id": engine_ev.target_id,
                        "sanitized_url": engine_ev.sanitized_url,
                        "title": engine_ev.title,
                        "extra": engine_ev.extra,
                        "ts": time.time(),
                    })
            _login_watcher_state["prev_targets"] = curr
            _login_watcher_state["prev_login_states"] = {
                tid: det.state for tid, det in login_states.items()
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("login_watcher loop exception: %s", exc)
        await asyncio.sleep(_LOGIN_WATCHER_INTERVAL_SEC)


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


def _apply_stale_tab_cleanup(targets: list[dict], cdp_port: int) -> dict:
    """plan_stale_tab_cleanup 결과를 실제 CDP/Playwright 로 실행.

    실패는 무시(best-effort). 사용자의 일반 Chrome 은 자동화 profile 분리
    덕분에 영향 없음.
    """
    plan = plan_stale_tab_cleanup(targets, keep_url="about:blank")
    closed: list[str] = []
    detected = len(plan["close_ids"]) + (
        1 if plan["navigate_keep_to"] else 0
    ) + (1 if plan["open_new_keep_url"] else 0)

    # 1. 잉여 탭 close
    if plan["close_ids"]:
        try:
            from scripts.browser_tab_monitor import _close_target

            for tid in plan["close_ids"]:
                try:
                    if _close_target(tid):
                        closed.append(tid)
                except Exception:
                    continue
        except Exception:
            pass

    # 2. keep 탭 navigate to about:blank
    if plan["navigate_keep_to"]:
        try:
            from scripts.web_connector import get_page

            get_page().goto(plan["navigate_keep_to"], timeout=10000)
        except Exception:
            pass

    # 3. 탭 0개면 새 탭 open
    if plan["open_new_keep_url"]:
        try:
            from scripts.web_connector import open_page

            page = open_page()
            try:
                page.goto("about:blank", timeout=10000)
            except Exception:
                pass
        except Exception:
            pass

    return {"closed": closed, "detected": detected, "plan": plan}


def plan_stale_tab_cleanup(
    targets: list[dict],
    *,
    keep_url: str = "about:blank",
) -> dict[str, list[str]]:
    """자동화 profile 의 stale 탭 정리 계획.

    자동화 Chrome 의 모든 탭은 같은 profile 이므로 모두 정리 대상.
    계획 규칙:
      - 탭 0개: open keep_url 1개 (caller 가 새 탭 생성)
      - 탭 1개 + url == keep_url: 변경 없음
      - 탭 1개 + url != keep_url: 그 탭을 keep_url 로 navigate
      - 탭 N개: 첫 탭 1개만 남기고 나머지 close, 남은 탭은 keep_url 로 navigate

    Returns:
        {
          "close_ids": [target_id, ...],
          "keep_id": str,
          "navigate_keep_to": str ("" 면 변경 불필요),
          "open_new_keep_url": bool,
        }
    """
    rows = [t for t in (targets or []) if isinstance(t, dict)]
    pages = [t for t in rows if t.get("type") == "page"]
    if not pages:
        return {"close_ids": [], "keep_id": "", "navigate_keep_to": keep_url,
                "open_new_keep_url": True}
    keep = pages[0]
    close_ids = [str(t.get("id", "")) for t in pages[1:] if t.get("id")]
    keep_url_cur = str(keep.get("url", "") or "")
    navigate_to = "" if keep_url_cur == keep_url else keep_url
    return {
        "close_ids": close_ids,
        "keep_id": str(keep.get("id", "") or ""),
        "navigate_keep_to": navigate_to,
        "open_new_keep_url": False,
    }


def _sync_store_with_targets(targets: list[dict]) -> dict[str, list[str]]:
    """현재 CDP target 목록과 session_store 의 탭을 정합."""
    _bs = browser_runtime_boundary.browser_session_store()

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
    _bs = browser_runtime_boundary.browser_session_store()

    paths = browser_runtime_boundary.resolve_paths()
    decision = await asyncio.to_thread(browser_runtime_boundary.decide_browser_start, paths)
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
    _bs = browser_runtime_boundary.browser_session_store()

    paths = browser_runtime_boundary.resolve_paths()
    decision = await asyncio.to_thread(browser_runtime_boundary.decide_browser_start, paths)

    if decision.action == browser_runtime_boundary.ACTION_ERROR_MULTIPLE:
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

    if decision.action == browser_runtime_boundary.ACTION_BLOCKED_BY_LOCK:
        await ws.send_json({
            "type": "browser_start_result",
            "ok": False,
            "error": decision.error or "LOCK_ACTIVE",
            "message_ko": decision.message_ko,
        })
        return

    if decision.action in (
        browser_runtime_boundary.ACTION_ATTACH_EXISTING,
        browser_runtime_boundary.ACTION_ATTACH_ORPHAN_CDP,
    ):
        _bs.start_session() if _bs.snapshot().get("status") != "BROWSER_RUNNING" else None
        targets = await _fetch_cdp_targets(paths.cdp_port)
        _sync_store_with_targets(targets)
        cleanup = await asyncio.to_thread(_apply_stale_tab_cleanup, targets, paths.cdp_port)
        # cleanup 후 다시 동기화
        targets = await _fetch_cdp_targets(paths.cdp_port)
        _sync_store_with_targets(targets)
        await _start_login_watcher()
        await ws.send_json({
            "type": "browser_start_result",
            "ok": True,
            "action": decision.action,
            "count": max(decision.count, 1),
            "message_ko": decision.message_ko,
            "tab_count": len(targets),
            "stale_tabs_closed": cleanup.get("closed", []),
            "stale_tabs_detected": cleanup.get("detected", 0),
        })
        return

    # ACTION_START_NEW → 실제 시작은 기존 web_connector._ensure_cdp_daemon 경로에 위임.
    # 이번 공정에서는 데몬을 직접 spawn 하지 않고 안내만 한다.
    if decision.action == browser_runtime_boundary.ACTION_START_NEW:
        import os as _os

        browser_runtime_boundary.write_lock_file(paths, _os.getpid())
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
            browser_runtime_boundary.clear_lock_file(paths)
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
    _bs = browser_runtime_boundary.browser_session_store()

    await _stop_login_watcher()
    paths = browser_runtime_boundary.resolve_paths()
    result = await asyncio.to_thread(browser_runtime_boundary.quit_automation_browsers, paths)
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
    _bs = browser_runtime_boundary.browser_session_store()

    paths = browser_runtime_boundary.resolve_paths()
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
    _bs = browser_runtime_boundary.browser_session_store()
    TAB_CLOSED = browser_runtime_boundary.TAB_CLOSED
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

    paths = browser_runtime_boundary.resolve_paths()

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


# ── 로그인 사전 체크 & 자동 재개 ─────────────────────────────────────────────

_LOGIN_BLOCKING_STATES = (
    "LOGIN_REQUIRED",
    "LOGIN_IN_PROGRESS",
    "LOGIN_ACTION_STARTED",
    "CHALLENGE_REQUIRED",
    "CONSENT_REQUIRED",
    "SESSION_EXPIRED",
)


def _ensure_engine():
    if _login_watcher_state.get("engine") is None:
        _login_watcher_state["engine"] = browser_runtime_boundary.create_login_auto_flow_engine(
            resume_executor=_default_resume_executor,
        )
    elif getattr(
        _login_watcher_state["engine"], "_resume_executor", None,
    ) is None:
        _login_watcher_state["engine"]._resume_executor = _default_resume_executor
    return _login_watcher_state["engine"]


def _current_blocking_login() -> tuple[str, str]:
    """가장 우선순위 높은 차단 상태 (state, target_id) 또는 ('','')."""
    states: dict[str, str] = _login_watcher_state.get("prev_login_states") or {}
    for tid, st in states.items():
        if st in _LOGIN_BLOCKING_STATES:
            return st, tid
    return "", ""


async def _login_precheck_and_enqueue(action_name: str, data: dict) -> bool:
    """현재 차단 상태가 있으면 engine 에 pending command 등록 후 True 반환.

    반환 True → 호출자는 자동화 실제 실행을 건너뛰고 LOGGED_IN 후 자동 재개를 기다림.
    """
    if data.get("_from_resume"):
        return False
    state, target_id = _current_blocking_login()
    if not state:
        return False

    engine = _ensure_engine()
    snapshots = _login_watcher_state.get("prev_targets") or []
    selected = browser_runtime_boundary.choose_login_target(
        snapshots,
        work_target_id=target_id,
    ) or target_id
    cmd = browser_runtime_boundary.create_pending_command(
        command_id=f"cmd_{action_name}_{int(time.time() * 1000)}",
        action=action_name,
        source_action=action_name,
        target_id_hint=selected,
        enqueued_at=time.time(),
        original_payload=dict(data),
        login_state_at_enqueue=state,
        resume_status="pending",
    )
    engine.enqueue_work_command(cmd)
    await _broadcast({
        "type": "login_target_selected",
        "target_id": selected,
        "extra": {"reason": "precheck", "blocking_state": state},
        "ts": time.time(),
    })
    await _broadcast({
        "type": "command_enqueued_pending_login",
        "command_id": cmd.command_id,
        "action": action_name,
        "blocking_state": state,
        "target_id": selected,
        "ts": time.time(),
    })
    return True


def _default_resume_executor(cmd) -> bool:
    """LOGGED_IN 감지 후 호출됨. 원래 action 을 재실행한다.

    engine 은 다른 스레드/태스크에서 호출될 수 있으므로 main event loop 로 schedule.
    payload 에 _from_resume=True 를 주입하여 무한 재진입을 방지한다.
    """
    payload = dict(cmd.original_payload or {})
    payload["_from_resume"] = True
    action = cmd.action

    dispatch_map = {
        "blog_write": _run_blog_write,
        "blog_confirm": lambda d: _run_blog_confirm(),
        "cafe_write": _run_cafe_write,
        "cafe_confirm": lambda d: _run_cafe_confirm(),
        "browser_action": _run_browser_action_from_payload,
    }
    runner = dispatch_map.get(action)
    if runner is None:
        return False

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return False

    try:
        loop.call_soon_threadsafe(lambda: asyncio.create_task(runner(payload)))
    except RuntimeError:
        # 동일 루프 안에서 호출된 경우
        asyncio.create_task(runner(payload))
    return True


async def _run_browser_action_from_payload(payload: dict) -> None:
    """resume 경로용 — broadcast 만 수행 (UI 응답은 원 ws 닫힌 후라 _broadcast 만 사용)."""
    await _execute_browser_action(payload, send_to=None)


async def _handle_browser_action(ws: WebSocket, data: dict) -> None:
    await _execute_browser_action(data, send_to=ws)


async def _execute_browser_action(payload: dict, *, send_to: WebSocket | None) -> None:
    """browser action 명령을 실행하고 표준 broadcast/응답을 수행."""
    ERR_TARGET_CLOSED = browser_runtime_boundary.ERR_TARGET_CLOSED
    ERR_TARGET_NOT_FOUND = browser_runtime_boundary.ERR_TARGET_NOT_FOUND

    req = browser_runtime_boundary.build_browser_action_request(payload)

    # 로그인 사전 체크 — resume 경로(_from_resume) 가 아니면 차단 시 enqueue
    if not payload.get("_from_resume"):
        if await _login_precheck_and_enqueue("browser_action", payload):
            msg = {
                "type": "browser_action_status",
                "status": "waiting_login",
                "command_id": req.command_id,
                "action_type": req.action_type,
            }
            if send_to is not None:
                await send_to.send_json(msg)
            await _broadcast(msg)
            return

    await _broadcast({
        "type": "browser_action_started",
        "command_id": req.command_id,
        "action_type": req.action_type,
        "target_id": req.target_id,
        "ts": time.time(),
    })

    try:
        result = await asyncio.to_thread(browser_runtime_boundary.execute_browser_action, req)
    except Exception as exc:
        result = None
        await _broadcast({
            "type": "browser_action_failed",
            "command_id": req.command_id,
            "action_type": req.action_type,
            "target_id": req.target_id,
            "error_code": "RUNNER_FAILED",
            "reason": f"{type(exc).__name__}: {exc}",
            "recoverable": True,
            "ts": time.time(),
        })
        if send_to is not None:
            await send_to.send_json({
                "type": "browser_action_result", "ok": False,
                "command_id": req.command_id, "error_code": "RUNNER_FAILED",
            })
        return

    result_dict = result.to_dict()
    if result.ok:
        await _broadcast({
            "type": "browser_action_completed",
            **result_dict,
            "ts": time.time(),
        })
    else:
        evt_type = "browser_action_failed"
        if result.error_code == ERR_TARGET_NOT_FOUND:
            evt_type = "target_not_found"
        elif result.error_code == ERR_TARGET_CLOSED:
            evt_type = "target_closed"
        await _broadcast({
            "type": evt_type,
            **result_dict,
            "ts": time.time(),
        })

    if send_to is not None:
        await send_to.send_json({
            "type": "browser_action_result",
            **result_dict,
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

    if await _login_precheck_and_enqueue("blog_write", data):
        await _broadcast({
            "type": "blog_status",
            "status": "waiting_login",
            "title": title,
        })
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

    if await _login_precheck_and_enqueue("cafe_write", data):
        await _broadcast({
            "type": "cafe_status",
            "status": "waiting_login",
            "title": title,
            "board": board,
        })
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


# ── 네이버 카페 목록 / 게시글 조회 ───────────────────────────────────────────────

async def _run_naver_cafe_list(ws) -> None:
    await ws.send_json({"type": "naver_cafe_list", "status": "loading"})
    loop = asyncio.get_event_loop()
    try:
        cafes = await loop.run_in_executor(None, _naver_cafe_list_sync)
        await ws.send_json({"type": "naver_cafe_list", "status": "done", "cafes": cafes})
    except Exception as exc:
        logger.error("naver_cafe_list error: %s", exc)
        await ws.send_json({"type": "naver_cafe_list", "status": "error", "error": str(exc)})


def _naver_cafe_list_sync() -> list:
    from scripts.web_connector import get_page
    from scripts.naver.cafe import NaverCafe
    return NaverCafe(get_page()).open_my_cafes()


async def _run_naver_cafe_posts(ws, data: dict) -> None:
    cafe_url = data.get("cafe_url", "")
    board_no = data.get("board_no", "")
    limit    = int(data.get("limit", 30))
    await ws.send_json({"type": "naver_cafe_posts", "status": "loading", "cafe_url": cafe_url})
    loop = asyncio.get_event_loop()
    try:
        posts = await loop.run_in_executor(None, _naver_cafe_posts_sync, cafe_url, board_no, limit)
        await ws.send_json({"type": "naver_cafe_posts", "status": "done", "cafe_url": cafe_url, "posts": posts})
    except Exception as exc:
        logger.error("naver_cafe_posts error: %s", exc)
        await ws.send_json({"type": "naver_cafe_posts", "status": "error", "error": str(exc)})


def _naver_cafe_posts_sync(cafe_url: str, board_no, limit: int) -> list:
    from scripts.web_connector import get_page
    from scripts.naver.cafe import NaverCafe
    return NaverCafe(get_page()).list_posts(cafe_url=cafe_url, board_no=board_no, limit=limit)


async def _run_naver_cafe_read(ws, data: dict) -> None:
    post_url = data.get("post_url", "")
    await ws.send_json({"type": "naver_cafe_read", "status": "loading"})
    loop = asyncio.get_event_loop()
    try:
        post = await loop.run_in_executor(None, _naver_cafe_read_sync, post_url)
        await ws.send_json({"type": "naver_cafe_read", "status": "done", "post": post})
    except Exception as exc:
        logger.error("naver_cafe_read error: %s", exc)
        await ws.send_json({"type": "naver_cafe_read", "status": "error", "error": str(exc)})


def _naver_cafe_read_sync(post_url: str) -> dict:
    from scripts.web_connector import get_page
    from scripts.naver.cafe import NaverCafe
    return NaverCafe(get_page()).read_post(post_url=post_url)


# ── 서버(8000) WebSocket 연결 및 Push 수신 ────────────────────────────────────
_server_ws: Any = None


async def _send_to_server(msg: dict) -> None:
    global _server_ws
    if _server_ws:
        try:
            await _server_ws.send(json.dumps(msg))
        except Exception as exc:
            logger.warning("server ws send error: %s", exc)


def _load_agent_credentials() -> tuple[str, str, str]:
    """config.json + token_store에서 server_url, agent_id, device_token 로드.

    반환: (server_url, agent_id, device_token) — 하나라도 없으면 빈 문자열 포함.
    """
    try:
        cfg = agent_runtime_boundary.load_desktop_config()
        if not cfg.is_complete():
            return "", "", ""
        tok = agent_runtime_boundary.load_device_token(cfg.server_url, cfg.agent_id)
        return cfg.server_url, cfg.agent_id, tok
    except Exception as exc:
        logger.warning("credentials load error: %s", exc)
        return "", "", ""


async def _connect_to_server() -> None:
    """서버 WebSocket에 연결 — agent_id/device_token 인증 포함, 재연결 루프."""
    global _server_ws
    import websockets  # type: ignore

    while True:
        server_url, agent_id, device_token = _load_agent_credentials()
        if not agent_id or not device_token:
            await _broadcast({"type": "system", "text": "⚠️ agent_id/token 미설정 — 서버 연결 건너뜀"})
            logger.warning("server ws skip: agent_id or device_token not configured")
            await asyncio.sleep(30)
            continue

        # server_url(https://...) → wss:// WebSocket URL 변환 (/api/v1/local-agents/ws)
        from urllib.parse import urlparse, urlunparse
        _p = urlparse(server_url)
        _ws_scheme = "wss" if _p.scheme == "https" else ("ws" if _p.scheme == "http" else _p.scheme or "ws")
        ws_url = urlunparse((_ws_scheme, _p.netloc, _p.path.rstrip("/") + "/api/v1/local-agents/ws", "", "", ""))

        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                # 인증
                await ws.send(json.dumps({
                    "type": "auth",
                    "agent_id": agent_id,
                    "device_token": device_token,
                }))
                try:
                    first = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                except asyncio.TimeoutError:
                    logger.error("server auth timeout")
                    await asyncio.sleep(5)
                    continue
                if first.get("type") != "auth_ok":
                    await _broadcast({"type": "system", "text": f"🔴 서버 인증 실패: {first.get('type')}"})
                    logger.error("server auth failed: %s", first.get("type"))
                    await asyncio.sleep(10)
                    continue

                _server_ws = ws
                await _broadcast({"type": "system", "text": f"🟢 서버 연결됨 (agent: {agent_id[:8]}…)"})
                logger.info("connected to server WebSocket (agent_id=%s)", agent_id)
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        await _on_server_message(msg)
                    except Exception as exc:
                        logger.warning("server message parse error: %s", exc)
        except Exception as exc:
            _server_ws = None
            await _broadcast({"type": "system", "text": "🔴 서버 연결 끊김 — 재연결 중…"})
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
    elif msg_type == "remote_control":
        await _handle_remote_control(msg)
    else:
        await _broadcast(msg)


async def _handle_remote_control(msg: dict) -> None:
    """서버에서 온 원격 제어 명령 처리 — 화이트리스트만 실행."""
    from .remote_access import ALLOWED_REMOTE_COMMANDS
    cmd = msg.get("command", "")
    req_id = msg.get("request_id", "")

    if cmd not in ALLOWED_REMOTE_COMMANDS:
        await _send_to_server({"type": "remote_control_result", "request_id": req_id,
                                "ok": False, "error": f"허용되지 않은 명령: {cmd}"})
        logger.warning("remote_control: blocked command=%s", cmd)
        return

    try:
        result = await _exec_remote_command(cmd, msg)
        await _send_to_server({"type": "remote_control_result", "request_id": req_id,
                                "ok": True, "command": cmd, "data": result})
    except Exception as exc:
        await _send_to_server({"type": "remote_control_result", "request_id": req_id,
                                "ok": False, "error": str(exc)})
        logger.error("remote_control error cmd=%s: %s", cmd, exc)


async def _exec_remote_command(cmd: str, msg: dict) -> dict:
    """허용된 원격 명령 실행 — 조회/열기만, 쓰기/삭제 금지."""
    import platform

    if cmd == "ping":
        return {"pong": True, "ts": time.time()}

    if cmd == "get_status":
        from .local_runner import LocalRunner
        runner = LocalRunner()
        return {
            "runner_state": runner.get_status(),
            "platform": platform.system(),
            "ui_clients": len(_ui_clients),
        }

    if cmd == "get_logs_tail":
        log_file = Path(__file__).parent.parent / "data" / "logs" / "app.log"
        if not log_file.exists():
            return {"lines": []}
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        # 민감 키 필터링
        _FORBIDDEN = {"token", "password", "secret", "authorization", "cookie"}
        safe = [l for l in lines if not any(k in l.lower() for k in _FORBIDDEN)]
        return {"lines": safe[-100:]}

    if cmd == "get_screenshot":
        import base64
        try:
            from scripts.browser.cdp_client import get_screenshot
            png = get_screenshot()
            return {"format": "png", "data": base64.b64encode(png).decode()}
        except Exception as exc:
            return {"error": str(exc)}

    if cmd == "open_url":
        import webbrowser
        url = str(msg.get("url", ""))
        if not url.startswith(("http://", "https://")):
            raise ValueError("허용되지 않은 URL 스킴")
        webbrowser.open(url)
        return {"opened": url}

    raise ValueError(f"미구현 명령: {cmd}")


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


# ── /api/v1/whoami (HAEHAN_WHOAMI_ROUTE_01) ────────────────────────────────
# Admin Mode role guard 가 호출하는 안전한 role 조회 엔드포인트.
# 응답에 token / device_token / registration_code / bearer / cookie / authorization /
# sk- / secret / password / api_key 키는 절대 포함되지 않는다.
# 127.0.0.1/local 접근이라는 이유로 admin 권한을 자동 부여하지 않는다 — 명시적 source 만 사용.

_WHOAMI_KNOWN_ROLES = frozenset({"any", "user", "viewer", "admin", "owner"})


def _resolve_whoami_role() -> tuple[str, str]:
    """role + source 결정.

    우선순위:
      1) HAEHAN_ROLE 환경변수 (KNOWN_ROLES 만)
      2) user_settings.json 의 role 필드 (있으면)
      3) "any" (default)

    127.0.0.1/local 이라는 이유로 admin 자동 부여 금지.
    """
    import os as _os
    env_role = _os.environ.get("HAEHAN_ROLE", "").strip().lower()
    if env_role in _WHOAMI_KNOWN_ROLES:
        return env_role, "env"
    try:
        from .user_settings import load_role  # type: ignore
        cfg_role = (load_role() or "").strip().lower()
        if cfg_role in _WHOAMI_KNOWN_ROLES:
            return cfg_role, "config"
    except Exception:
        pass
    return "any", "default"


@app.get("/api/v1/whoami")
async def whoami():
    """현재 사용자 role 조회 — Admin Mode role guard 용.

    응답 키는 ok / role / admin / source 로 제한. 민감 정보 절대 미포함.
    """
    role, source = _resolve_whoami_role()
    return {
        "ok": True,
        "role": role,
        "admin": role in ("admin", "owner"),
        "source": source,
    }


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


# ── 에이전트 등록 API ─────────────────────────────────────────────────────────

@app.post("/agent/register")
async def agent_register(request: Request):
    """등록 코드로 에이전트를 서버에 등록하고 device_token을 저장.

    body: { "registration_code": "...", "server_url": "https://..." }
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "요청 파싱 실패"}

    reg_code = (body.get("registration_code") or "").strip()
    server_url = (body.get("server_url") or "https://haehan-ai.kr/orchestrator").strip()
    if not reg_code:
        return {"ok": False, "error": "registration_code 필요"}

    try:
        import platform

        meta, device_token = agent_runtime_boundary.register_with_code(
            server_url=server_url,
            registration_code=reg_code,
            host=platform.node(), os_name=platform.system(), version="0.1.0"
        )
        agent_runtime_boundary.save_device_token(server_url, meta.agent_id, device_token)
        cfg = agent_runtime_boundary.load_desktop_config()
        cfg.server_url = server_url
        cfg.agent_id = meta.agent_id
        agent_runtime_boundary.save_desktop_config(cfg)
        logger.info("agent registered: agent_id=%s", meta.agent_id)
        await _broadcast({"type": "system", "text": f"✅ 등록 완료 — agent_id: {meta.agent_id[:12]}…"})
        # 서버 WS 재연결 트리거
        asyncio.create_task(_connect_to_server())
        return {"ok": True, "agent_id": meta.agent_id}
    except Exception as exc:
        logger.error("register error: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.get("/agent/status")
async def agent_status():
    """현재 등록된 에이전트 정보 반환 (token 제외)."""
    try:
        cfg = agent_runtime_boundary.load_desktop_config()
        server_connected = _server_ws is not None
        return {
            "ok": True,
            "server_url": cfg.server_url,
            "agent_id": cfg.agent_id,
            "is_complete": cfg.is_complete(),
            "server_connected": server_connected,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── CAD bridge registry/status + lifecycle ───────────────────────────────────
# CAD-DESKTOP-HUB-CAD-BRIDGE-REGISTRY-STATUS-01 (status route)
# CAD-DESKTOP-HUB-CAD-BRIDGE-LIFECYCLE-01 (start/stop/restart + runnerState)
from .cad_bridge_registry import (
    check_status as _cad_bridge_check_status,
    load_default_config as _cad_bridge_load_default_config,
)
from .cad_bridge_runner import CadBridgeRunner

# Module-level singleton runner. proxy / WS action 미추가 — HTTP only.
_cad_bridge_runner: Optional[CadBridgeRunner] = None


def _get_cad_bridge_runner() -> CadBridgeRunner:
    """Lazy singleton — 첫 호출 시 default config 로 인스턴스 생성."""
    global _cad_bridge_runner
    if _cad_bridge_runner is None:
        _cad_bridge_runner = CadBridgeRunner()
    return _cad_bridge_runner


def _safe_runner_snapshot() -> dict:
    """runner snapshot 을 안전하게 추출. 예외 시 빈 dict — desktop 서버 보호."""
    try:
        return _get_cad_bridge_runner().snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cad_bridge runner snapshot error: %s", exc)
        return {"state": "error", "lastError": str(exc)}


@app.get("/cad/bridge/status")
async def get_cad_bridge_status():
    """CAD local_bridge 상태 조회 (read-only) + runner 내부 state.

    절대 process start/stop/kill 하지 않는다. HTTP GET openapi.json 만
    시도하고 실패는 STOPPED / UNREACHABLE 등으로 격리한다. desktop hub
    서버는 어떤 경우에도 본 호출로 인해 죽지 않는다.

    응답에 `runnerState` 필드 1개 additive — lifecycle runner 의
    snapshot(state/pid/port/cadRepoPath/lastError). 기존 registry/status
    의 envelope (status/host/port/detail/signaturePathsPresent) 는
    그대로 유지.
    """
    try:
        config = _cad_bridge_load_default_config()
        status = _cad_bridge_check_status(config)
        result = status.to_dict()
    except Exception as exc:  # noqa: BLE001 — 서버 안정성 우선
        logger.warning("cad_bridge_status unexpected error: %s", exc)
        result = {
            "status": "UNKNOWN",
            "host": None,
            "port": None,
            "detail": f"unexpected error: {type(exc).__name__}",
            "signaturePathsPresent": 0,
        }
    # additive: runnerState 1 필드만 추가
    result["runnerState"] = _safe_runner_snapshot()
    return result


@app.post("/cad/bridge/start")
async def post_cad_bridge_start():
    """CAD bridge subprocess 기동 시도.

    request body 없음 — 외부 PID / 임의 명령 인자 0건. cad_repo_path
    미설정 / forbidden port / spawn 실패 등은 모두 200 + snapshot 으로
    격리. desktop 서버는 어떤 경우에도 본 호출로 죽지 않는다.
    """
    try:
        runner = _get_cad_bridge_runner()
        started = runner.start()
        return {"started": bool(started), "snapshot": runner.snapshot()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cad_bridge_start unexpected error: %s", exc)
        return {
            "started": False,
            "snapshot": {"state": "error", "lastError": str(exc)},
        }


@app.post("/cad/bridge/stop")
async def post_cad_bridge_stop():
    """CAD bridge subprocess 종료 — 자기가 spawn 한 process 만 terminate.

    외부 PID 인자 없음. body 없음. desktop.local_server 등 다른
    프로세스에는 어떤 영향도 주지 않는다.
    """
    try:
        runner = _get_cad_bridge_runner()
        stopped = runner.stop()
        return {"stopped": bool(stopped), "snapshot": runner.snapshot()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cad_bridge_stop unexpected error: %s", exc)
        return {
            "stopped": False,
            "snapshot": {"state": "error", "lastError": str(exc)},
        }


@app.post("/cad/bridge/restart")
async def post_cad_bridge_restart():
    """stop + start. body 없음. 자기 process 외에 영향 0건."""
    try:
        runner = _get_cad_bridge_runner()
        ok = runner.restart()
        return {"restarted": bool(ok), "snapshot": runner.snapshot()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cad_bridge_restart unexpected error: %s", exc)
        return {
            "restarted": False,
            "snapshot": {"state": "error", "lastError": str(exc)},
        }


# ── CAD bridge proxy (READ_ONLY + CANDIDATE_PAYLOAD allow-list 만) ────────
# CAD-DESKTOP-HUB-CAD-BRIDGE-PROXY-01.
# /cad/bridge/proxy/{path:path} — upstream http://127.0.0.1:8766/{path}
# passthrough. mutating keyword / allow-list 외 path 는 403 차단.
from .cad_bridge_proxy import proxy_cad_bridge_request as _cad_bridge_proxy_request


@app.get("/cad/bridge/proxy/{path:path}")
async def get_cad_bridge_proxy(path: str, request: Request):
    """GET passthrough to CAD local_bridge — read-only allow-list only."""
    return await _cad_bridge_proxy_request(
        method="GET",
        path=path,
        query=str(request.url.query) or None,
        body=None,
        headers=dict(request.headers),
    )


@app.post("/cad/bridge/proxy/{path:path}")
async def post_cad_bridge_proxy(path: str, request: Request):
    """POST passthrough to CAD local_bridge — CANDIDATE_PAYLOAD allow-list only."""
    body = await request.body()
    return await _cad_bridge_proxy_request(
        method="POST",
        path=path,
        query=str(request.url.query) or None,
        body=body,
        headers=dict(request.headers),
    )




# ── 신규 Desktop Shell — /app-new (Phase 2 smoke route) ─────────────────────
# 기존 / 와 /index.html은 건드리지 않음. 새 shell은 /app-new 에서만 서빙.
# 환경변수 HAEHAN_DESKTOP_UI=new_shell 이면 WebView/Launcher가 이 URL을 사용.
@app.get("/app-new")
async def new_shell():
    """신규 Desktop Shell 조회 전용 HTML (Phase 2).

    HTTP 재진입(self-call) 데드락을 피하기 위해 내부 서비스 함수를 직접 호출한다.
    실행 버튼(AI run / CAD start) 은 비활성화 상태로만 표시.
    """
    from desktop.ui_new.shell_html import build_html_from_data
    from desktop.local_agent_service import local_agent_health as _la_health, local_agent_preflight as _preflight
    import time, json as _json

    # ── 내부 서비스 직접 호출 (HTTP 재진입 없음) ──
    la_health_data   = _la_health()
    preflight_data   = _preflight()

    # agent/status: device_token 기반, 직접 읽기
    try:
        from desktop.tray_runtime import check_registration_status
        reg = check_registration_status()
        agent_data = {
            "ok": reg.registered,
            "agent_id": getattr(reg, "agent_id", ""),
            "server_url": getattr(reg, "server_url", ""),
            "server_connected": getattr(reg, "registered", False),
        }
    except Exception:
        agent_data = {"ok": False, "agent_id": "", "server_connected": False}

    # whoami: role 파악
    try:
        from desktop.admin_webview import resolve_current_role
        role = resolve_current_role()
    except Exception:
        role = "unknown"

    # logs: 최근 로그 라인
    try:
        from desktop.status_provider import get_recent_logs
        log_lines = get_recent_logs(n=15)
    except Exception:
        log_lines = []

    data = {
        "health": {"ok": True, "service": "haehan-local-server", "ts": int(time.time())},
        "agent": agent_data,
        "la_health": la_health_data if isinstance(la_health_data, dict) else la_health_data.__dict__,
        "preflight": preflight_data if isinstance(preflight_data, dict) else _json.loads(_json.dumps(preflight_data, default=str)),
        "whoami": {"ok": True, "role": role},
        "logs": {"lines": log_lines},
    }

    html = build_html_from_data(data)
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ── Health endpoint — 항상 JSON 반환 (SPA fallback 차단) ─────────────────────
@app.get("/health")
async def health_check():
    """로컬 서버 상태 확인. SPA fallback이 아닌 JSON만 반환."""
    import time
    from desktop.app_config import LOCAL_HOST, LOCAL_PORT
    return {
        "ok": True,
        "service": "haehan-local-server",
        "host": LOCAL_HOST,
        "port": LOCAL_PORT,
        "ts": int(time.time()),
    }


# ── index.html — 항상 최신 버전 서빙 (캐시 금지) ───────────────────────────────
@app.get("/")
@app.get("/index.html")
async def serve_index():
    """index.html을 no-cache 헤더와 함께 반환 — WebView2 캐시 방지."""
    index_path = _UI_DIR / "index.html"
    content = index_path.read_bytes()
    return Response(
        content=content,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ── CAD 원격 서버 API 프록시 (/api/v1 → cad.haehan-ai.kr) ───────────────────
# 프론트엔드(로컬 서빙)가 /api/v1/* 호출 시 원격 서버로 투명하게 전달
_CAD_REMOTE_BASE = "https://cad.haehan-ai.kr"

_HOP_BY_HOP = frozenset([
    "host", "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade",
])


async def _proxy_to_remote(method: str, path: str, request: Request) -> Response:
    url = f"{_CAD_REMOTE_BASE}/api/v1/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
    body = await request.body() if method in ("POST", "PUT", "PATCH") else None
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.request(method, url, headers=headers, content=body)
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _HOP_BY_HOP}
        return Response(content=resp.content, status_code=resp.status_code,
                        headers=resp_headers, media_type=resp.headers.get("content-type"))
    except Exception as exc:
        logger.warning("remote proxy error %s %s: %s", method, url, exc)
        return Response(content=b'{"detail":"REMOTE_PROXY_ERROR"}',
                        status_code=502, media_type="application/json")


# ── 로컬 AI Agent 엔드포인트 (/local-agent) ──────────────────────────────────

@app.get("/local-agent/health")
async def local_agent_health():
    """로컬 AI (Anthropic SDK / Claude Code CLI) 가용 여부 반환."""
    from .local_agent_service import local_agent_health as _health
    return _health()


@app.get("/local-agent/preflight")
async def local_agent_preflight():
    """로컬 AI 실행 사전 점검.

    providers(anthropic_sdk, claude_cli) 중 하나라도 가용이면 can_run=true.
    optional(cad, cdp) 은 down 이어도 can_run 에 영향 없음.
    api_key 원문은 절대 반환하지 않으며 api_key_set(boolean) 만 반환.
    """
    from .local_agent_service import local_agent_preflight as _preflight
    return _preflight()


@app.post("/local-agent/run")
async def local_agent_run(request: Request):
    """로컬 AI + 로컬 MCP를 사용하여 에이전트 실행.

    Body JSON:
        prompt (str, 필수)
        model  (str, optional) — 기본 claude-sonnet-4-5
        use_mcp (bool, optional) — 기본 False; direct MCP is blocked
    """
    from .local_agent_service import run_local_agent as _run
    try:
        body = await request.json()
    except Exception:
        body = {}
    result = await _run(body)
    status_code = 200 if result.get("ok") else 500
    return Response(
        content=__import__("json").dumps(result, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


@app.get("/api/v1/{path:path}")
async def proxy_api_get(path: str, request: Request):
    return await _proxy_to_remote("GET", path, request)


@app.post("/api/v1/{path:path}")
async def proxy_api_post(path: str, request: Request):
    return await _proxy_to_remote("POST", path, request)


@app.put("/api/v1/{path:path}")
async def proxy_api_put(path: str, request: Request):
    return await _proxy_to_remote("PUT", path, request)


@app.delete("/api/v1/{path:path}")
async def proxy_api_delete(path: str, request: Request):
    return await _proxy_to_remote("DELETE", path, request)


# ── SPA fallback — /api, /cad, /ws, /proxy 외 모든 경로를 index.html로 ────────
# /assets/* 는 실제 정적 파일로 서빙 (catch-all보다 먼저 처리).
# FastAPI @app.get 라우트가 app.mount 보다 우선하므로 여기서 분기한다.
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """React SPA 라우터용 catch-all.
    /assets/* 는 실제 파일을 올바른 MIME 타입으로 반환.
    그 외 경로는 index.html fallback.

    보호: API/도구 경로는 SPA fallback 금지.
    /api, /cad, /ws, /proxy, /agent, /local-agent, /logs, /health 로 시작하는
    경로가 여기까지 도달하면 404 JSON을 반환한다.
    """
    import mimetypes
    # API 경로 보호 — SPA fallback으로 흡수 금지
    _API_PREFIXES = (
        "api/", "cad/", "ws/", "proxy/", "agent/",
        "local-agent/", "logs", "health",
    )
    if any(full_path == p.rstrip("/") or full_path.startswith(p) for p in _API_PREFIXES):
        return Response(
            content=b'{"detail":"NOT_FOUND","path":"/' + full_path.encode() + b'"}',
            status_code=404,
            media_type="application/json",
        )
    if full_path.startswith("assets/"):
        asset_file = _UI_DIR / full_path
        if asset_file.is_file():
            mime, _ = mimetypes.guess_type(str(asset_file))
            return Response(
                content=asset_file.read_bytes(),
                media_type=mime or "application/octet-stream",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
    index_path = _UI_DIR / "index.html"
    if not index_path.exists():
        return Response(content=b"index.html not found", status_code=404)
    return Response(
        content=index_path.read_bytes(),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ── 정적 파일 서빙 — 모든 API/WS 라우트 등록 후 마지막에 마운트 ────────────────
# index.html 이 /assets/... 경로로 JS/CSS 요청하므로 루트("/")에 마운트해야 함
app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


def run():
    from desktop.app_config import LOCAL_PORT, effective_bind_host
    bind_host = effective_bind_host()
    logging.basicConfig(level=logging.INFO)
    logger.info("local server binding %s:%s", bind_host, LOCAL_PORT)
    uvicorn.run(app, host=bind_host, port=LOCAL_PORT, log_level="warning")
