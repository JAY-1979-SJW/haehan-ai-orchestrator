"""쇼핑 통계 — 판매/재고 대시보드 (READ 전용)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (2026-08-14: [4]는 저장소 밖 C:\work 를 가리켰음)
sys.path.insert(0, str(ROOT))

from scripts.common.gate import check  # noqa: E402  (sys.path 설정 후 import)


def dashboard_summary() -> dict:
    """판매 대시보드 요약 — AUTO 게이트."""
    check("shopping_dashboard_read", risk="auto")
    # 기존 analytics_dashboard 모듈 위임
    return {"status": "delegated", "module": "analytics_dashboard"}


def inventory_status() -> dict:
    """재고 현황 조회 — AUTO 게이트."""
    check("shopping_inventory_read", risk="auto")
    return {"status": "delegated", "module": "inventory_monitor"}
