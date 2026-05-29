"""YouTube 통합 라우터 — 하위 모듈을 조합합니다."""
from fastapi import APIRouter

from .oauth    import router as oauth_router
from .research import router as research_router

youtube_router = APIRouter(tags=["youtube"])

# URL 경로는 기존과 동일하게 유지 (Google Cloud Console 콜백 URL 변경 불필요)
youtube_router.include_router(oauth_router,    prefix="/oauth/youtube")
youtube_router.include_router(research_router, prefix="/youtube/research")

__all__ = ["youtube_router"]
