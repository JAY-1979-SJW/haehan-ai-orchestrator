"""하위 호환 re-export — ai_orchestrator.routers.registry가 이 경로로 import합니다."""
from .youtube.router import youtube_router  # noqa: F401

__all__ = ["youtube_router"]
