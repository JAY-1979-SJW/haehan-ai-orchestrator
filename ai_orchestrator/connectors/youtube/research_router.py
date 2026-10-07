"""하위 호환 re-export. 실구현은 connectors/youtube/research.py 참조."""
from fastapi import APIRouter

from ai_orchestrator.connectors.youtube.research import router as _router

youtube_research_router = APIRouter(prefix="/youtube/research", tags=["youtube-research"])
youtube_research_router.include_router(_router)

__all__ = ["youtube_research_router"]
