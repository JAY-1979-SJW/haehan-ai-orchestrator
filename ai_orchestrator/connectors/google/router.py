"""Google 통합 라우터 — 서브도메인·워크스페이스·YouTube 조합."""

from fastapi import APIRouter

from .actions import router as actions_router
from .chat import router as chat_router
from .subdomain import router as subdomain_router
from .workspace import router as workspace_router
from .youtube import router as youtube_router

google_router = APIRouter(tags=["google"])

google_router.include_router(subdomain_router, prefix="/google")
google_router.include_router(workspace_router, prefix="/google/workspace")
google_router.include_router(chat_router, prefix="/google")
google_router.include_router(actions_router, prefix="/google/tools")
google_router.include_router(youtube_router, prefix="/google/youtube")

__all__ = ["google_router"]
