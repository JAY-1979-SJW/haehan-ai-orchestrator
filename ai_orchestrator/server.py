import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .logging_setup import setup_logging
from .router import router
from .config import APP_HOST, APP_PORT
from .connectors.naver_search_runner import schedule_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("haehan-ai-orchestrator 시작 | host=%s port=%s", APP_HOST, APP_PORT)
    task = asyncio.create_task(schedule_loop())

    # CDP 팝업 백그라운드 폴러 시작 (CDP 미연결 시 자동 재시도)
    try:
        import sys, pathlib
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
        if poller:
            try:
                stop_poller()
            except Exception:
                pass
        logger.info("haehan-ai-orchestrator 종료")


app = FastAPI(title="haehan-ai-orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(router)

from .browser_gate_middleware import BrowserGateMiddleware  # noqa: E402
app.add_middleware(BrowserGateMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "file://"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ai_orchestrator.server:app", host=APP_HOST, port=APP_PORT, reload=False)
