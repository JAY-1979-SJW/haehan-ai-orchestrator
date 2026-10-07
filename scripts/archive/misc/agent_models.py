"""에이전트 입출력 모델.

공통 request/response 인터페이스:
- ``AgentRequest``: action + (url | site_key + target_url) + options
- ``AgentResult``: {ok, action, data, error} — 모든 action 이 동일 형식 반환

이번 표준화 단계에서 AgentRequest 는 웹/시크릿 양쪽 호출 패턴을 하나의
구조로 수렴시키기 위해 필드가 늘었다. 호환을 위해 기존 ``params`` 는 남겨둔다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRequest:
    action: str
    # URL 기반 action 전용 (open_page_readonly / inspect_page)
    url: str = ""
    # 시크릿 기반 action 전용 (login_with_secret / inspect_after_login)
    site_key: str = ""
    target_url: str = ""
    # 향후 excel/cad/mcp 등 범용 옵션 전달용
    options: dict = field(default_factory=dict)
    # backward-compat 예비 필드
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "url": self.url,
            "site_key": self.site_key,
            "target_url": self.target_url,
            "options": dict(self.options or {}),
        }

    @classmethod
    def from_kwargs(
        cls,
        action: str,
        url: str = "",
        *,
        site_key: str = "",
        target_url: str = "",
        options: dict | None = None,
        **_ignored: Any,
    ) -> AgentRequest:
        """app.run(...) 의 가변 kwargs 를 표준 request 로 정규화."""
        return cls(
            action=str(action) if action is not None else "",
            url=url if isinstance(url, str) else "",
            site_key=site_key if isinstance(site_key, str) else "",
            target_url=target_url if isinstance(target_url, str) else "",
            options=dict(options) if isinstance(options, dict) else {},
        )


@dataclass
class AgentResult:
    ok: bool
    action: str
    data: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "data": self.data,
            "error": self.error,
        }
