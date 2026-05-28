"""플랫폼/인프라 자동화 서브패키지.

포함:
  - session_manager: 세션 관리 + 자동 재로그인
  - error_recovery: 에러 자동 복구
  - scheduler: 정기 실행 스케줄러
  - image_processor: 이미지 자동 처리
"""
from __future__ import annotations

__all__ = [
    "SessionManager",
    "ErrorRecovery",
    "Scheduler",
    "ImageProcessor",
]


def __getattr__(name):
    if name == "SessionManager":
        from .session_manager import SessionManager
        return SessionManager
    if name == "ErrorRecovery":
        from .error_recovery import ErrorRecovery
        return ErrorRecovery
    if name == "Scheduler":
        from .scheduler import Scheduler
        return Scheduler
    if name == "ImageProcessor":
        from .image_processor import ImageProcessor
        return ImageProcessor
    raise AttributeError(name)
