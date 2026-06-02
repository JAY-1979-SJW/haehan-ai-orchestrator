"""로컬 데스크탑 앱 전용 FastAPI 서버 (포트 8765) — 진입점.

모듈 구조:
  _broadcast.py        공유 상태: UI 클라이언트 목록, broadcast, server WS send
  login_watcher.py     로그인 watcher + 자동 재개 엔진
  blog_cafe_actions.py 블로그/카페/네이버 카페 자동화 액션
  browser_routes.py    브라우저 lifecycle WS 핸들러 + CDP 유틸
  ws_ui.py             /ws/ui WebSocket + UI 메시지 dispatch
  ws_server.py         서버 WS 연결 + Push 수신 + 원격 제어
  routes/agent.py      /agent/register, /agent/status
  routes/system.py     /health, /logs, /whoami, /app-new, /proxy/admin
  routes/proxy.py      /api/v1 CAD 프록시 + SPA fallback
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from .remote_access import is_enabled as _remote_enabled
from .remote_access import verify_token as _verify_token
from .ws_server import connect_to_server

logger = logging.getLogger(__name__)


# ── UI 디렉토리 탐색 ──────────────────────────────────────────────────────────


def _resolve_ui_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False):
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


# ── 원격 접속 미들웨어 ────────────────────────────────────────────────────────

_EXEMPT_PATHS = {"/ws/ui", "/health"}


class RemoteAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        if request.scope.get("type") == "websocket":
            client_host = (request.scope.get("client") or ["127.0.0.1"])[0]
        else:
            client_host = (request.client.host if request.client else "") or ""
        if client_host in ("127.0.0.1", "::1", "localhost"):
            return await call_next(request)
        if not _remote_enabled():
            return StarletteResponse("원격 접속이 비활성화되어 있습니다.", status_code=403)
        if request.url.path in _EXEMPT_PATHS or request.url.path.startswith("/ws/"):
            token = request.query_params.get("token", "")
        else:
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not _verify_token(token):
            return StarletteResponse("액세스 토큰 불일치", status_code=401)
        return await call_next(request)


# ── lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    server_task = asyncio.create_task(connect_to_server())
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


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Haehan Desktop Local Server", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(RemoteAccessMiddleware)


@app.exception_handler(HTTPException)
async def _http_exc(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_exc(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def _generic_exc(request: Request, exc: Exception):
    logger.error("처리되지 않은 예외 [%s %s]: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "내부 서버 오류"})


# ── 라우터 include ────────────────────────────────────────────────────────────

from .routes.agent import router as _agent_router
from .routes.proxy import build_spa_router
from .routes.proxy import router as _proxy_router
from .routes.system import router as _system_router
from .ws_ui import router as _ws_ui_router

app.include_router(_ws_ui_router)
app.include_router(_agent_router)
app.include_router(_system_router)

# ── 로컬 AI Agent 라우터 ──────────────────────────────────────────────────────
from fastapi import APIRouter as _APIRouter

_local_agent_router = _APIRouter()


@_local_agent_router.get("/local-agent/health")
async def local_agent_health():
    from .local_agent_service import local_agent_health as _health

    return _health()


@_local_agent_router.get("/local-agent/preflight")
async def local_agent_preflight():
    from .local_agent_service import local_agent_preflight as _preflight

    return _preflight()


@_local_agent_router.post("/local-agent/run")
async def local_agent_run(request: Request):
    import json

    from .local_agent_service import run_local_agent as _run

    try:
        body = await request.json()
    except Exception:
        body = {}
    result = await _run(body)
    from fastapi.responses import Response

    return Response(
        content=json.dumps(result, ensure_ascii=False),
        status_code=200 if result.get("ok") else 500,
        media_type="application/json",
    )


app.include_router(_local_agent_router)

# ── CAD bridge 라우터 ─────────────────────────────────────────────────────────
from .cad_bridge_proxy import proxy_cad_bridge_request as _cad_bridge_proxy_request
from .cad_bridge_registry import (
    check_status as _cad_bridge_check_status,
)
from .cad_bridge_registry import (
    load_default_config as _cad_bridge_load_default_config,
)
from .cad_bridge_runner import CadBridgeRunner

_cad_bridge_runner: CadBridgeRunner | None = None


def _get_cad_runner() -> CadBridgeRunner:
    global _cad_bridge_runner
    if _cad_bridge_runner is None:
        _cad_bridge_runner = CadBridgeRunner()
    return _cad_bridge_runner


def _safe_runner_snapshot() -> dict:
    try:
        return _get_cad_runner().snapshot()
    except Exception as exc:
        logger.warning("cad_bridge runner snapshot error: %s", exc)
        return {"state": "error", "lastError": str(exc)}


_cad_bridge_api = _APIRouter()


@_cad_bridge_api.get("/cad/bridge/status")
async def get_cad_bridge_status():
    try:
        result = _cad_bridge_check_status(_cad_bridge_load_default_config()).to_dict()
    except Exception as exc:
        logger.warning("cad_bridge_status unexpected error: %s", exc)
        result = {
            "status": "UNKNOWN",
            "host": None,
            "port": None,
            "detail": f"unexpected error: {type(exc).__name__}",
            "signaturePathsPresent": 0,
        }
    result["runnerState"] = _safe_runner_snapshot()
    return result


@_cad_bridge_api.post("/cad/bridge/start")
async def post_cad_bridge_start():
    try:
        runner = _get_cad_runner()
        return {"started": bool(runner.start()), "snapshot": runner.snapshot()}
    except Exception as exc:
        return {"started": False, "snapshot": {"state": "error", "lastError": str(exc)}}


@_cad_bridge_api.post("/cad/bridge/stop")
async def post_cad_bridge_stop():
    try:
        runner = _get_cad_runner()
        return {"stopped": bool(runner.stop()), "snapshot": runner.snapshot()}
    except Exception as exc:
        return {"stopped": False, "snapshot": {"state": "error", "lastError": str(exc)}}


@_cad_bridge_api.post("/cad/bridge/restart")
async def post_cad_bridge_restart():
    try:
        runner = _get_cad_runner()
        return {"restarted": bool(runner.restart()), "snapshot": runner.snapshot()}
    except Exception as exc:
        return {"restarted": False, "snapshot": {"state": "error", "lastError": str(exc)}}


@_cad_bridge_api.get("/cad/bridge/proxy/{path:path}")
async def get_cad_bridge_proxy(path: str, request: Request):
    return await _cad_bridge_proxy_request(
        method="GET", path=path, query=str(request.url.query) or None, body=None, headers=dict(request.headers)
    )


@_cad_bridge_api.post("/cad/bridge/proxy/{path:path}")
async def post_cad_bridge_proxy(path: str, request: Request):
    body = await request.body()
    return await _cad_bridge_proxy_request(
        method="POST", path=path, query=str(request.url.query) or None, body=body, headers=dict(request.headers)
    )


app.include_router(_cad_bridge_api)

# ── CAD 로컬 라우터 (optional — CAD_SERVER_PATH 설정 시) ─────────────────────
try:
    import os as _os
    import sys as _sys

    _cad_program_path = _os.environ.get("CAD_SERVER_PATH", r"C:\work\03. cad-program")
    if _cad_program_path not in _sys.path:
        _sys.path.insert(0, _cad_program_path)
    from fastapi import APIRouter as _CADR
    from fastapi import Request as _Req
    from fastapi.responses import JSONResponse as _JSONResponse
    from flask import Flask as _Flask

    from cad_router import cad_bp as _cad_bp

    _flask_app = _Flask("cad_local")
    _flask_app.register_blueprint(_cad_bp)
    _cad_local = _CADR(prefix="/api/v1/cad")

    @_cad_local.get("/projects")
    async def _cad_projects():
        with _flask_app.test_request_context("/api/v1/cad/projects"):
            from cad_router import list_projects

            r = list_projects()
            return _JSONResponse(content=r.get_json(), status_code=r.status_code)

    @_cad_local.get("/{project}/status")
    async def _cad_status(project: str, discipline: str = "건축"):
        with _flask_app.test_request_context(f"/api/v1/cad/{project}/status?discipline={discipline}"):
            from cad_router import project_status

            r = project_status(project)
            return _JSONResponse(content=r.get_json(), status_code=r.status_code)

    @_cad_local.get("/{project}/rooms")
    async def _cad_rooms(project: str, discipline: str = "건축", drawing_no: str = "", min_area: float = 0.5):
        with _flask_app.test_request_context(
            f"/api/v1/cad/{project}/rooms?discipline={discipline}&drawing_no={drawing_no}&min_area={min_area}"
        ):
            from cad_router import list_rooms

            r = list_rooms(project)
            return _JSONResponse(content=r.get_json(), status_code=r.status_code)

    @_cad_local.post("/{project}/analyze")
    async def _cad_analyze(project: str, req: _Req):
        body = await req.body()
        with _flask_app.test_request_context(
            f"/api/v1/cad/{project}/analyze", method="POST", data=body, content_type="application/json"
        ):
            from cad_router import analyze_project

            r = analyze_project(project)
            return _JSONResponse(content=r.get_json(), status_code=r.status_code)

    app.include_router(_cad_local)
    logger.info("CAD 로컬 라우터 마운트 완료 (/api/v1/cad)")
except Exception as _e:
    logger.warning("CAD 로컬 라우터 마운트 실패 (원격 프록시로 폴백): %s", _e)

# ── /api/v1 catch-all 프록시 + SPA fallback (항상 마지막) ────────────────────
app.include_router(_proxy_router)
app.include_router(build_spa_router(_UI_DIR))
app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


def run():
    from desktop.app_config import LOCAL_PORT, effective_bind_host

    bind_host = effective_bind_host()
    logging.basicConfig(level=logging.INFO)
    logger.info("local server binding %s:%s", bind_host, LOCAL_PORT)
    uvicorn.run(app, host=bind_host, port=LOCAL_PORT, log_level="warning")
