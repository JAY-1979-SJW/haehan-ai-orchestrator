"""하위 호환 re-export. 실구현은 connectors/youtube/oauth.py 참조."""
from .connectors.youtube.oauth import router as _router
from fastapi import APIRouter

youtube_oauth_router = APIRouter(prefix="/oauth/youtube", tags=["youtube-oauth"])
youtube_oauth_router.include_router(_router)

__all__ = ["youtube_oauth_router"]
