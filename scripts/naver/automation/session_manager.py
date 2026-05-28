"""Re-export stub — 실제 구현은 platform/session_manager.py 로 이동.

하위 호환성 유지: 기존 import 경로 그대로 동작.
"""
from scripts.naver.automation.platform.session_manager import (  # noqa: F401
    SessionManager,
)

__all__ = ["SessionManager"]
