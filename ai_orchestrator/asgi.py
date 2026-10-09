import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_orchestrator.connectors.naver_search.naver_search_runner import schedule_loop
from ai_orchestrator.paths import (
    bootstrap as _runtime_bootstrap,  # noqa: F401 - 저장소(DB)가 열리기 전에 데이터 폴더 준비·이행(맨 먼저 실행돼야 함)
)

from .core import config
from .core.config import APP_HOST, APP_PORT
from .core.logging_setup import setup_logging
from .routers import app_actions
from .routers.registry import router

logger = logging.getLogger(__name__)


def _hide_own_console() -> None:
    """Windows: 자기 콘솔 창을 숨긴다(부모 콘솔은 유지 → subprocess 자식이 상속해
    매번 새 콘솔 창을 띄우지 않음 = 작업 중 터미널 깜빡임 방지). 콘솔이 없으면 무시."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        print(
            f"[console] hwnd={hwnd} (자식 상속용 콘솔 {'있음·숨김' if hwnd else '없음!'})", file=sys.stderr, flush=True
        )
    except Exception as exc:  # noqa: BLE001 — 콘솔 숨김 실패는 무시(기능 영향 없음)
        logger.debug("콘솔 숨김 실패: %s", type(exc).__name__)
        pass


_hide_own_console()


def _write_server_discovery_file() -> None:
    """실제로 기동한 host:port를 파일에 기록 — 클라이언트(local_agent 등)가 포트 리터럴을
    직접 하드코딩하는 대신 이 파일을 먼저 읽어 자동으로 찾아가게 한다(2026-09-30 추가,
    defect_index #18: 파일마다 다른 포트 기본값이 흩어져 있던 문제의 근본 대책 — 단일
    소스(config.py APP_PORT)를 고치는 것과 별개로, "지금 실제로 뜬 서버가 어디 있는지"를
    가장 확실하게 아는 쪽은 그 서버 자신이므로 시작 시점에 직접 알린다).
    lifespan startup 시점엔 uvicorn이 이미 소켓 바인딩을 마친 뒤이므로 이 값을 그대로
    믿어도 안전하다. 쓰기 실패는 비치명적(기존 하드코딩 기본값으로 폴백됨) — 서버 기동을
    막지 않는다."""
    import json
    import os
    import time
    from pathlib import Path

    try:
        path = Path(__file__).resolve().parents[1] / "data" / "runtime" / "server_info.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"host": APP_HOST, "port": APP_PORT, "pid": os.getpid(), "started_at": time.time()}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        logger.warning("[server-discovery] server_info.json 기록 실패(비치명적): %s", e)


def _start_scheduled_job_loop() -> asyncio.Task | None:
    try:
        from .scheduler.scheduled_job_loop import scheduled_job_loop

        return asyncio.create_task(scheduled_job_loop())
    except Exception as e:  # noqa: BLE001 - FastAPI 서버 기동 시 백그라운드 스케줄러 시작 실패 처리 - 로그만 남기고 해당 기능 비활성화, 보안 판정과 무관
        logger.warning("예약 작업 루프 시작 실패 (무시): %s", e)
        return None


def _resume_agent_dispatch() -> None:
    """서버 재시작 전에 승인된 채 끝나지 않은 AI 작업 분배가 있으면 러너를 다시 띄운다(실패해도 기동을 막지 않음)."""
    try:
        # 등록 모듈(routers/registry)을 거쳐 부른다 — asgi(최상위)가 기능 폴더를 직접 import 하면 최상위 ↔ agent_dispatch 순환이 생긴다
        from .routers.registry import resume_agent_dispatch_on_startup

        if resume_agent_dispatch_on_startup():
            logger.info("AI 작업 분배 러너 재개(승인된 진행 중 분배안 있음)")
    except Exception as e:  # noqa: BLE001 - FastAPI 서버 기동 시 작업 분배 러너 재개 실패 처리 - 로그만 남기고 기동 계속, 보안 판정과 무관
        logger.warning("AI 작업 분배 러너 재개 실패 (무시): %s", e)


def _start_user_job_loops() -> asyncio.Task | None:
    """사용자 작업 계열 백그라운드 시작: 예약 작업 루프 + 승인된 AI 작업 분배 재개."""
    _resume_agent_dispatch()
    return _start_scheduled_job_loop()


async def _stop_task(task: asyncio.Task | None) -> None:
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _check_jwt_secret() -> None:
    """AUTH_ENABLED 인데 JWT_SECRET 이 없거나 짧으면 알린다. JWT_SECRET_REQUIRED=true 면 없을 때 시작을 막는다.

    없으면 프로세스마다 임의 키라 재시작·재배포 때 모든 로그인이 풀리고, 워커가 둘 이상이면 로그인이 간헐적으로 실패한다.
    config 는 호출 시점에 읽는다(시험에서 값을 바꿀 수 있게)."""
    if not config.AUTH_ENABLED:
        return
    if not config.JWT_SECRET_CONFIGURED:
        message = (
            "[보안] AUTH_ENABLED=true 인데 JWT_SECRET 이 설정되지 않았습니다 — 프로세스마다 임의 키를 쓰므로 "
            "재시작·재배포 때 모든 로그인이 풀립니다. .env 에 32자 이상 무작위 JWT_SECRET 을 설정하세요."
        )
        if config.JWT_SECRET_REQUIRED:
            raise RuntimeError(message + " (JWT_SECRET_REQUIRED=true 라 시작을 중단합니다)")
        logger.error(message)
    elif len(config.JWT_SECRET) < config.JWT_SECRET_MIN_LENGTH:
        logger.error(
            "[보안] JWT_SECRET 이 %d자로 너무 짧습니다(권장 %d자 이상). 추측 가능한 키는 토큰 위조로 이어집니다.",
            len(config.JWT_SECRET),
            config.JWT_SECRET_MIN_LENGTH,
        )


def _connect_gate_audit() -> None:
    """게이트 판정 감사 기록(op_log)을 앱 시작점에서 연결한다.

    게이트 핵심(gate_core)은 scripts 를 import 하지 않으므로(R2d-2 설계서 §4, 순환 해소) 감사 싱크를 여기서 주입한다.
    scripts.common.gate(shim)를 import 하는 CLI·스크립트 경로는 shim 이 같은 싱크를 등록한다.
    """
    from tools.gates.gate_core import set_audit_sink

    def _audit(name: str, **fields) -> None:
        from scripts.common.op_log import log_op

        log_op(name, **fields)

    set_audit_sink(_audit)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _check_jwt_secret()
    _connect_gate_audit()
    logger.info("haehan-ai-orchestrator 시작 | host=%s port=%s", APP_HOST, APP_PORT)
    _write_server_discovery_file()
    _LOOPBACK_ONLY = {"127.0.0.1", "::1", "localhost"}
    if APP_HOST not in _LOOPBACK_ONLY:
        logger.warning(
            "[보안] APP_HOST=%s — loopback 외 인터페이스 노출 상태입니다. 운영/패키징 환경에서는 127.0.0.1로 기동하세요.",
            APP_HOST,
        )
    task = asyncio.create_task(schedule_loop())

    # 커뮤니티 자율 분석 스케줄러 (등록 사이트 주기 수집·분석·리포트)
    try:
        from .connectors.community_scheduler import community_schedule_loop

        community_task = asyncio.create_task(community_schedule_loop())
    except Exception as e:  # noqa: BLE001 - FastAPI 서버 기동/종료 시 백그라운드 스케줄러(커뮤니티/gonobi/CDP폴러) 시작 실패 처리 - 로그만 남기고 해당 기능 비활성화, 보안 판정과 무관
        community_task = None
        logger.warning("커뮤니티 스케줄러 시작 실패 (무시): %s", e)

    # gonobi 블로그 주기적 수집 스케줄러
    try:
        from .connectors.naver_blog.gonobi_scheduler import gonobi_schedule_loop

        gonobi_task = asyncio.create_task(gonobi_schedule_loop())
    except Exception as e:  # noqa: BLE001 - FastAPI 서버 기동/종료 시 백그라운드 스케줄러(커뮤니티/gonobi/CDP폴러) 시작 실패 처리 - 로그만 남기고 해당 기능 비활성화, 보안 판정과 무관
        gonobi_task = None
        logger.warning("gonobi 스케줄러 시작 실패 (무시): %s", e)

    # 사용자 예약 작업 루프 (앱 화면에서 만든 예약을 실행 시각에 실행)
    scheduled_job_task = _start_user_job_loops()

    # CDP 팝업 백그라운드 폴러 시작 (CDP 미연결 시 자동 재시도)
    try:
        import pathlib
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
        from scripts.naver.smartstore.navigation.cdp_popup_manager import start_poller, stop_poller

        poller = start_poller(interval=5)
        logger.info("CDP 팝업 폴러 시작 (interval=5s)")
    except Exception as e:  # noqa: BLE001 - FastAPI 서버 기동/종료 시 백그라운드 스케줄러(커뮤니티/gonobi/CDP폴러) 시작 실패 처리 - 로그만 남기고 해당 기능 비활성화, 보안 판정과 무관
        poller = None
        logger.warning("CDP 팝업 폴러 시작 실패 (무시): %s", e)

    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if community_task:
            community_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await community_task
        if gonobi_task:
            gonobi_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await gonobi_task
        await _stop_task(scheduled_job_task)
        if poller:
            # 종료 시 폴러 정리 실패는 무시 — 프로세스가 어차피 종료되는 중
            with contextlib.suppress(Exception):
                stop_poller()
        logger.info("haehan-ai-orchestrator 종료")


app = FastAPI(title="haehan-ai-orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(router)
app_actions.configure_app(app)  # 앱 액션 목록이 라우트를 훑을 앱을 주입(routers 가 asgi 를 import 하지 않는다)

from tools.gates.browser_gate_middleware import BrowserGateMiddleware  # noqa: E402

app.add_middleware(BrowserGateMiddleware)

# CORS — 데스크톱(frozen) 앱은 localhost만 허용(외부 차단). 서버는 정상 도메인 허용.
import sys as _sys  # noqa: E402

_is_desktop = getattr(_sys, "frozen", False)
_cors_regex = (
    r"http://(localhost|127\.0\.0\.1)(:\d+)?"
    if _is_desktop
    else r"https?://([a-z0-9-]+\.)*haehan-ai\.kr|http://(localhost|127\.0\.0\.1)(:\d+)?"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "file://",
    ],
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_orchestrator.asgi:app", host=APP_HOST, port=APP_PORT, reload=False)
