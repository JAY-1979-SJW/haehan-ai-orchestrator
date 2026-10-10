"""다중 채널 알림 통합 — 슬랙/디스코드/이메일/SMS/푸시.

지원 채널:
  - Slack (Incoming Webhook)
  - Discord (Webhook)
  - Email (네이버 메일 통한 발송)
  - 톡톡 (네이버 톡톡)
  - Console (로컬 알림)

환경변수:
  SLACK_WEBHOOK_URL
  DISCORD_WEBHOOK_URL
"""

from __future__ import annotations

import json
import os
import urllib.request

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class NotificationHub:
    """다중 채널 통합 알림 발송."""

    def __init__(self, page=None):
        self.page = page
        self.slack_url = os.environ.get("SLACK_WEBHOOK_URL")
        self.discord_url = os.environ.get("DISCORD_WEBHOOK_URL")

    # ── 슬랙 ──────────────────────────────────────────────────────────

    def send_slack(self, message: str, channel: str | None = None, webhook_url: str | None = None) -> dict:
        url = webhook_url or self.slack_url
        if not url:
            return {"ok": False, "error": "no_slack_webhook"}
        payload = {"text": message}
        if channel:
            payload["channel"] = channel
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
            log_critical("OTHER", "Slack 알림", channel=channel, mode="notify_slack")
            return {"ok": True, "channel": channel}
        except Exception as e:  # noqa: BLE001 - 슬랙/디스코드 알림 발송 실패를 ok:False 오류로 반환 — best-effort 알림, 실패해도 원 작업에는 영향 없음
            return {"ok": False, "error": str(e)[:80]}

    # ── 디스코드 ──────────────────────────────────────────────────────

    def send_discord(self, message: str, username: str | None = None, webhook_url: str | None = None) -> dict:
        url = webhook_url or self.discord_url
        if not url:
            return {"ok": False, "error": "no_discord_webhook"}
        payload = {"content": message}
        if username:
            payload["username"] = username
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
            log_critical("OTHER", "Discord 알림", mode="notify_discord")
            return {"ok": True}
        except Exception as e:  # noqa: BLE001 - 슬랙/디스코드 알림 발송 실패를 ok:False 오류로 반환 — best-effort 알림, 실패해도 원 작업에는 영향 없음
            return {"ok": False, "error": str(e)[:80]}

    # ── 네이버 메일 ──────────────────────────────────────────────────

    def send_email(self, to: str, subject: str, body: str) -> dict:
        if not self.page:
            return {"ok": False, "error": "page_required"}
        # scripts.naver.mail 은 설계상 읽기전용(패키지 __init__.py 문서화: 발송/답장/삭제 등
        # 쓰기 동작을 모듈 레벨에서 금지) 이라 NaverMail(발송용 클래스)이 애초에 존재한 적이
        # 없음 — 예전엔 여기서 바로 ImportError 로 죽었음(2026-09-29 defect_index #38,
        # mail_automation.py의 동일 패턴과 함께 발견). 다른 send_* 메서드들과 같은
        # {"ok": False, "error": ...} 계약으로 맞춰 명확히 실패시킨다.
        return {"ok": False, "error": "naver_mail_send_not_implemented"}

    # ── 네이버 톡톡 ──────────────────────────────────────────────────

    def send_talk(self, partner: str, message: str) -> dict:
        if not self.page:
            return {"ok": False, "error": "page_required"}
        from scripts.naver.common.talk import NaverTalk

        talk = NaverTalk(self.page)
        return talk.send_message(partner, message, confirm=True)

    # ── 콘솔/로컬 ────────────────────────────────────────────────────

    def send_console(self, message: str, level: str = "info") -> dict:
        getattr(_log, level if level in ("debug", "info", "warning", "error") else "info")("[notify] %s", message)
        return {"ok": True}

    # ── 통합 발송 ────────────────────────────────────────────────────

    def notify(self, message: str, channels: list[str] | None = None, level: str = "info", **kwargs) -> dict:
        """다중 채널 동시 발송.

        channels: ["slack", "discord", "console", "email", "talk"]
        kwargs: 채널별 추가 인자 (e.g. email_to, talk_partner)
        """
        channels = channels or ["console"]
        results = {}
        for ch in channels:
            if ch == "slack":
                results["slack"] = self.send_slack(message, channel=kwargs.get("slack_channel"))
            elif ch == "discord":
                results["discord"] = self.send_discord(message, username=kwargs.get("discord_username"))
            elif ch == "console":
                results["console"] = self.send_console(message, level=level)
            elif ch == "email":
                to = kwargs.get("email_to")
                subject = kwargs.get("email_subject", "[자동 알림]")
                if to:
                    results["email"] = self.send_email(to, subject, message)
            elif ch == "talk":
                partner = kwargs.get("talk_partner")
                if partner:
                    results["talk"] = self.send_talk(partner, message)
        ok = all(r.get("ok") for r in results.values())
        log_critical(
            "OTHER", f"다중채널 알림: {list(results.keys())}", channels=list(results.keys()), ok=ok, mode="notify_multi"
        )
        return {"ok": ok, "results": results}
