"""네이버 서비스 고급 자동화 패키지.

기본 wrapper(blog/mail/cafe/...) 위에 구축되는 고차 자동화:
  - review_automation: 스토어/플레이스/블로그 리뷰 자동 답변
  - order_automation: 스마트스토어 주문 자동 처리
  - session_manager: 세션 만료 감지 + 자동 재로그인
  - workflow: 서비스 간 워크플로우 (블로그→톡톡, 주문→카페 등)

사용:
  from scripts.naver.automation import OrderAutomation

(MailAutomation 은 호출처가 없어 scripts/archive/naver/automation/ 로 보관했다 — 도구 지도 B1·결정 ⑤)
"""
from __future__ import annotations

# 서브패키지 노출
from scripts.naver.automation import content, integration, platform  # noqa: F401

__all__ = [
    "ReviewAutoResponder",
    "OrderAutomation",
    "SessionManager",
    "Workflow",
    "CSVImporter",
    "InventoryMonitor",
    "ImageProcessor",
    "Scheduler",
    "AnalyticsDashboard",
    "AIResponder",
    "CompetitorAnalysis",
    "SEOOptimizer",
    "NotificationHub",
    "ErrorRecovery",
]


def _load_core_export(name):
    """지연 import 대상(앞 그룹). 해당 이름이 아니면 None."""
    if name == "ReviewAutoResponder":
        from .review_automation import ReviewAutoResponder
        return ReviewAutoResponder
    if name == "OrderAutomation":
        from .order_automation import OrderAutomation
        return OrderAutomation
    if name == "SessionManager":
        from .session_manager import SessionManager
        return SessionManager
    if name == "Workflow":
        from .workflow import Workflow
        return Workflow
    if name == "CSVImporter":
        from .csv_import import CSVImporter
        return CSVImporter
    if name == "InventoryMonitor":
        from .inventory_monitor import InventoryMonitor
        return InventoryMonitor
    if name == "ImageProcessor":
        from .image_processor import ImageProcessor
        return ImageProcessor
    return None


def _load_extra_export(name):
    """지연 import 대상(뒤 그룹). 해당 이름이 아니면 None."""
    if name == "Scheduler":
        from .scheduler import Scheduler
        return Scheduler
    if name == "AnalyticsDashboard":
        from .analytics_dashboard import AnalyticsDashboard
        return AnalyticsDashboard
    if name == "AIResponder":
        from .ai_responder import AIResponder
        return AIResponder
    if name == "CompetitorAnalysis":
        from .competitor_analysis import CompetitorAnalysis
        return CompetitorAnalysis
    if name == "SEOOptimizer":
        from .seo_optimizer import SEOOptimizer
        return SEOOptimizer
    if name == "NotificationHub":
        from .notification_hub import NotificationHub
        return NotificationHub
    if name == "ErrorRecovery":
        from .error_recovery import ErrorRecovery
        return ErrorRecovery
    return None


def __getattr__(name):
    for loader in (_load_core_export, _load_extra_export):
        found = loader(name)
        if found is not None:
            return found
    raise AttributeError(name)
