"""외부 연동/통합 자동화 서브패키지.

포함:
  - ai_responder: AI 기반 자동 응답
  - notification_hub: 다중 채널 알림
  - workflow: 서비스 간 워크플로우
(mail_automation 은 호출처가 없어 scripts/archive/naver/automation/integration/ 로 보관했다 — 도구 지도 B1·결정 ⑤)
"""
from __future__ import annotations

__all__ = [
    "AIResponder",
    "NotificationHub",
    "Workflow",
]


def __getattr__(name):
    if name == "AIResponder":
        from .ai_responder import AIResponder
        return AIResponder
    if name == "NotificationHub":
        from .notification_hub import NotificationHub
        return NotificationHub
    if name == "Workflow":
        from .workflow import Workflow
        return Workflow
    raise AttributeError(name)
