"""스마트스토어 자동화 서브패키지.

포함:
  - csv_import: CSV/Excel → 일괄 등록
  - inventory_monitor: 재고 모니터링
  - order_automation: 주문 자동 처리
  - analytics_dashboard: 분석 대시보드
  - competitor_analysis: 경쟁사 분석
"""

from __future__ import annotations

__all__ = [
    "AnalyticsDashboard",
    "CSVImporter",
    "CompetitorAnalysis",
    "InventoryMonitor",
    "OrderAutomation",
]


def __getattr__(name):
    if name == "CSVImporter":
        from .csv_import import CSVImporter

        return CSVImporter
    if name == "InventoryMonitor":
        from .inventory_monitor import InventoryMonitor

        return InventoryMonitor
    if name == "OrderAutomation":
        from .order_automation import OrderAutomation

        return OrderAutomation
    if name == "AnalyticsDashboard":
        from .analytics_dashboard import AnalyticsDashboard

        return AnalyticsDashboard
    if name == "CompetitorAnalysis":
        from .competitor_analysis import CompetitorAnalysis

        return CompetitorAnalysis
    raise AttributeError(name)
