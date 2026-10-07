"""재고 자동 모니터링 — 임계치 기반 알림.

기능:
  - 정기 재고 조회
  - 임계치 이하 상품 자동 감지
  - 메일/톡톡 자동 알림
  - 자동 재주문 가이드 생성
"""

from __future__ import annotations

import re

from playwright.sync_api import Page

from scripts.critical_logger import log_critical
from scripts.logger import get_logger

_log = get_logger(__name__)


class InventoryMonitor:
    """재고 임계치 모니터링."""

    def __init__(self, page: Page):
        self.page = page

    def check_low_stock(self, threshold: int = 10) -> dict:
        """재고가 임계치 이하인 상품 찾기."""
        from scripts.naver.smartstore import NaverSmartStore

        store = NaverSmartStore(self.page)
        r = store.list_products(limit=200)
        if not r.get("ok"):
            return r

        headers = r.get("headers", [])
        rows = r.get("rows", [])

        # 재고 컬럼 찾기
        stock_idx = next((i for i, h in enumerate(headers) if "재고" in h), None)
        name_idx = next((i for i, h in enumerate(headers) if "상품" in h and "명" in h), 0)

        low_stock = []
        for row in rows:
            if stock_idx is None or stock_idx >= len(row):
                continue
            stock_str = str(row[stock_idx]).replace(",", "").strip()
            m = re.search(r"\d+", stock_str)
            if m is None:
                continue
            try:
                stock = int(m.group())
            except ValueError:
                continue
            if stock <= threshold:
                low_stock.append(
                    {
                        "name": row[name_idx] if name_idx < len(row) else "",
                        "stock": stock,
                        "row": row,
                    }
                )

        low_stock.sort(key=lambda x: x["stock"])
        log_critical(
            "OTHER",
            f"재고 모니터링: 임계치({threshold}) 이하 {len(low_stock)}개",
            threshold=threshold,
            low_count=len(low_stock),
            mode="inventory_check",
        )
        return {
            "ok": True,
            "total": len(rows),
            "threshold": threshold,
            "low_count": len(low_stock),
            "items": low_stock,
        }

    def alert_low_stock(
        self, threshold: int = 10, mail_to: str | None = None, talk_partner: str | None = None, send: bool = False
    ) -> dict:
        """임계치 이하 재고 메일/톡톡 알림."""
        check = self.check_low_stock(threshold)
        if not check.get("ok") or check.get("low_count", 0) == 0:
            return check

        items = check["items"]
        body = "재고 부족 상품 목록\n\n" + "\n".join(
            f"  {i + 1}. {it['name'][:40]} — 재고 {it['stock']}개" for i, it in enumerate(items[:20])
        )
        if check["low_count"] > 20:
            body += f"\n\n... 외 {check['low_count'] - 20}개"

        results = []
        from scripts.naver import NaverServices

        n = NaverServices(self.page)

        if mail_to:
            r = n.mail.compose(mail_to, f"[재고 부족] {check['low_count']}건", body, send=send)
            results.append({"type": "mail", "result": r})
        if talk_partner:
            r = n.talk.send_message(talk_partner, body[:500], confirm=send)
            results.append({"type": "talk", "result": r})

        log_critical("OTHER", f"재고 알림 발송: {check['low_count']}개", send=send, mode="inventory_alert")
        return {**check, "alerts": results}

    def build_reorder_plan(self, threshold: int = 10, target_stock: int = 100) -> dict:
        """재고 부족 상품의 재주문 계획 생성."""
        check = self.check_low_stock(threshold)
        if not check.get("ok"):
            return check
        plans = []
        for item in check["items"]:
            need = target_stock - item["stock"]
            if need > 0:
                plans.append(
                    {
                        "name": item["name"],
                        "current": item["stock"],
                        "target": target_stock,
                        "order_qty": need,
                    }
                )
        return {"ok": True, "plans": plans, "total_qty": sum(p["order_qty"] for p in plans)}
