import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
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
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("haehan-ai-orchestrator 종료")


app = FastAPI(title="haehan-ai-orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ai_orchestrator.server:app", host=APP_HOST, port=APP_PORT, reload=False)
