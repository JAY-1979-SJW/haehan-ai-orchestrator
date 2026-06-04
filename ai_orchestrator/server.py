import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import APP_HOST, APP_PORT
from .connectors.naver_search_runner import schedule_loop
from .logging_setup import setup_logging
from .router import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("haehan-ai-orchestrator 시작 | host=%s port=%s", APP_HOST, APP_PORT)
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
    except Exception as e:
        community_task = None
        logger.warning("커뮤니티 스케줄러 시작 실패 (무시): %s", e)

    # CDP 팝업 백그라운드 폴러 시작 (CDP 미연결 시 자동 재시도)
    try:
        import pathlib
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
        from scripts.naver.smartstore.navigation.cdp_popup_manager import start_poller, stop_poller

        poller = start_poller(interval=5)
        logger.info("CDP 팝업 폴러 시작 (interval=5s)")
    except Exception as e:
        poller = None
        logger.warning("CDP 팝업 폴러 시작 실패 (무시): %s", e)

    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if community_task:
            community_task.cancel()
            try:
                await community_task
            except asyncio.CancelledError:
                pass
        if poller:
            try:
                stop_poller()
            except Exception:  # noqa: S110
                pass
        logger.info("haehan-ai-orchestrator 종료")


app = FastAPI(title="haehan-ai-orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(router)

from .browser_gate_middleware import BrowserGateMiddleware  # noqa: E402

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

    uvicorn.run("ai_orchestrator.server:app", host=APP_HOST, port=APP_PORT, reload=False)
