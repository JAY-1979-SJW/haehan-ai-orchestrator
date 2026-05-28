"""쇼핑 통계 — 판매/재고 대시보드 (READ 전용)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.gate import check


def dashboard_summary() -> dict:
    """판매 대시보드 요약 — AUTO 게이트."""
    check("shopping_dashboard_read", risk="auto")
    # 기존 analytics_dashboard 모듈 위임
    from scripts.naver.automation.smartstore.analytics_dashboard import (
        AnalyticsDashboard,
    )
    return {"status": "delegated", "module": "analytics_dashboard"}


def inventory_status() -> dict:
    """재고 현황 조회 — AUTO 게이트."""
    check("shopping_inventory_read", risk="auto")
    from scripts.naver.automation.smartstore.inventory_monitor import (
        InventoryMonitor,
    )
    return {"status": "delegated", "module": "inventory_monitor"}
