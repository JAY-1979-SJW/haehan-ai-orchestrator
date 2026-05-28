"""Re-export stub — 실제 구현은 integration/ai_responder.py 로 이동.

하위 호환성 유지: 기존 import 경로 그대로 동작.
"""
from scripts.naver.automation.integration.ai_responder import (  # noqa: F401
    AIResponder,
)

__all__ = ["AIResponder"]
