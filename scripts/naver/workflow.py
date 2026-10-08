"""서비스 간 워크플로우 자동화.

여러 네이버 서비스를 연결한 자동화:
  - 블로그 발행 → 톡톡 공지
  - 스토어 신규 주문 → 메일 알림 + 카페 공지
  - 캘린더 일정 → 톡톡 메시지 예약
  - 마이박스 신규 파일 → 메일 알림
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class Workflow:
    """서비스 간 통합 워크플로우."""

    def __init__(self, page: Page):
        self.page = page
        from scripts.naver.services import NaverServices

        self.n = NaverServices(page)

    # ── 블로그 → SNS / 톡톡 ─────────────────────────────────────────────

    def blog_publish_and_notify(
        self, blog_data: dict, notify_targets: list[str] | None = None, send_notify: bool = False
    ) -> dict:
        """블로그 글 발행 + 발행 후 톡톡/메일 공지.

        blog_data: BlogWriter.write_post 매개변수
        notify_targets: 톡톡 파트너 이름 리스트
        send_notify: True 시 실제 발송 (기본 False — 안전)
        """
        # 1. 블로그 발행 (또는 임시저장)
        bw = self.n.blog
        if not bw.open():
            return {"ok": False, "error": "blog_open_failed"}

        bw.set_title(blog_data["title"])
        bw.write_body(blog_data["body"])
        if blog_data.get("tags"):
            bw.set_tags(blog_data["tags"])

        publish_result = bw.save_draft()  # 안전: 임시저장
        if not publish_result.get("ok"):
            return {"ok": False, "step": "blog", "result": publish_result}

        # 2. 톡톡 공지
        notify_results = []
        if notify_targets:
            for target in notify_targets:
                msg = f"[새 글 발행] {blog_data['title']}\n블로그에서 확인하세요!"
                r = self.n.talk.send_message(target, msg, confirm=send_notify)
                notify_results.append({"target": target, "result": r})
                time.sleep(2)

        log_critical(
            "OTHER",
            f"블로그+톡톡 워크플로우: {blog_data['title'][:30]}",
            notify_count=len(notify_targets or []),
            send_notify=send_notify,
            mode="blog_workflow",
        )
        return {
            "ok": True,
            "blog": publish_result,
            "notifications": notify_results,
        }

    # ── 스토어 주문 → 알림 ─────────────────────────────────────────────

    def new_orders_to_alerts(
        self,
        mail_recipient: str | None = None,
        cafe_url: str | None = None,
        cafe_board: int | str = "",
        send_alerts: bool = False,
    ) -> dict:
        """스토어 신규 주문 → 메일/카페 공지."""
        from scripts.naver.smartstore.automation.order_automation import OrderAutomation

        oa = OrderAutomation(self.page)
        orders = oa.fetch_new_orders()
        if not orders.get("ok"):
            return orders

        new_count = orders.get("new_count", 0)
        if new_count == 0:
            return {"ok": True, "new_count": 0, "alerts_sent": 0}

        alerts = []

        # 메일 알림
        if mail_recipient:
            # scripts.naver.mail 은 읽기전용이라 NaverMail(발송 클래스)이 존재한 적이 없다 — 예전엔 서비스 객체의 mail 접근에서
            # ImportError 로 죽었다(defect_index #38 과 같은 원인). smartstore/automation/inventory_monitor 와 같은 계약으로 명확히 실패시킨다.
            r = {"ok": False, "error": "naver_mail_send_not_implemented"}
            alerts.append({"type": "mail", "result": r})

        # 카페 공지
        if cafe_url and cafe_board:
            title = f"신규 주문 {new_count}건 발송 대기"
            body = f"발송 대기 주문이 {new_count}건 있습니다."
            r = self.n.cafe.write_post(cafe_url, cafe_board, title, body, send=send_alerts)
            alerts.append({"type": "cafe", "result": r})

        log_critical(
            "OTHER",
            f"신규 주문 알림 워크플로우: {new_count}건",
            new_count=new_count,
            alerts=len(alerts),
            send=send_alerts,
            mode="order_alert_workflow",
        )
        return {"ok": True, "new_count": new_count, "alerts": alerts}

    # ── 일정 → 메시지 예약 ────────────────────────────────────────────

    def calendar_to_talk(self, days_ahead: int = 1, notify_partner: str | None = None, send: bool = False) -> dict:
        """다음 N일 일정을 톡톡으로 알림."""
        events = self.n.calendar.list_events()
        if not events:
            return {"ok": True, "events": 0, "sent": False}

        message = "📅 예정 일정:\n" + "\n".join(f"• {e.get('title', '')} {e.get('time', '')}" for e in events[:10])
        if notify_partner:
            r = self.n.talk.send_message(notify_partner, message, confirm=send)
            log_critical("OTHER", f"일정 알림: {len(events)}개", to=notify_partner, send=send, mode="calendar_alert")
            return {"ok": True, "events": len(events), "talk": r}
        return {"ok": True, "events": len(events), "message_preview": message[:200]}

    # ── 정기 모니터링 (반복) ───────────────────────────────────────────

    def schedule_daily_check(self, hour: int = 9) -> dict:
        """매일 N시에 신규 주문/리뷰/문의 자동 체크 (예약 표준).

        Note: 실제 실행은 cron/systemd/scheduled task로.
        """
        return {
            "ok": True,
            "hint": "이 함수는 단발성 체크용. 정기 실행은 cron 또는 ScheduleWakeup 사용",
            "cron_example": f"0 {hour} * * *  python scripts/run_daily_naver_check.py",
        }
