"""하위 호환 re-export — ai_orchestrator.router가 이 경로로 import합니다."""
from .smartstore.router import smartstore_router  # noqa: F401

__all__ = ["smartstore_router"]
