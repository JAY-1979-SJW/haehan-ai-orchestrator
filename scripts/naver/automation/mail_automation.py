"""Re-export stub — 실제 구현은 integration/mail_automation.py 로 이동.

하위 호환성 유지: 기존 import 경로 그대로 동작.
"""
from scripts.naver.automation.integration.mail_automation import (  # noqa: F401
    MailAutomation,
)

__all__ = ["MailAutomation"]
