"""하위 호환 re-export — ai_orchestrator.router가 이 경로로 import합니다."""
from .google.router import google_router  # noqa: F401

__all__ = ["google_router"]
