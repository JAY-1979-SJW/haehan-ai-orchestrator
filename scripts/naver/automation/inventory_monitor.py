"""Re-export stub — 실제 구현은 smartstore/inventory_monitor.py 로 이동.

하위 호환성 유지: 기존 import 경로 그대로 동작.
"""
from scripts.naver.automation.smartstore.inventory_monitor import (  # noqa: F401
    InventoryMonitor,
)

__all__ = ["InventoryMonitor"]
