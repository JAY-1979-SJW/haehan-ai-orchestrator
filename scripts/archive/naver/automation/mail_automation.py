"""Re-export stub (보관) — 실제 구현은 같은 보관 폴더의 integration/mail_automation.py.

호출처가 없어 scripts/archive 로 옮겼다(도구 지도 B1·결정 ⑤). 새 작업에서 import 금지.
"""

from scripts.archive.naver.automation.integration.mail_automation import MailAutomation

__all__ = ["MailAutomation"]
