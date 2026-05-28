"""Re-export stub — 실제 구현은 smartstore/analytics_dashboard.py 로 이동.

하위 호환성 유지: 기존 import 경로 그대로 동작.
"""
from scripts.naver.automation.smartstore.analytics_dashboard import (  # noqa: F401
    AnalyticsDashboard,
)

__all__ = ["AnalyticsDashboard"]
