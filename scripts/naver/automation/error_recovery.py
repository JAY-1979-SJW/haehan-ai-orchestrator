"""Re-export stub — 실제 구현은 platform/error_recovery.py 로 이동.

하위 호환성 유지: 기존 import 경로 그대로 동작.
"""
from scripts.naver.automation.platform.error_recovery import (  # noqa: F401
    ErrorRecovery,
)

__all__ = ["ErrorRecovery"]
