"""ExamplePortalConnector.

실제 외부 사이트에 접속하지 않는다. 구조 검증 목적.
- secrets/sites/example_portal.env 및 secrets/browser_state/example_portal.json
  파일의 존재 여부만 확인
- 브라우저 기동 가능성은 probe_launch() 로만 확인
- health_check 결과는 파일/기동 상태에 따라 healthy / degraded / unconfigured 로 달라진다
"""
from __future__ import annotations

import time
from typing import ClassVar, Literal

from . import secrets_policy
from .browser import probe_launch
from .connector import SiteConnector
from .models import SiteHealthStatus


class ExamplePortalConnector(SiteConnector):
    name: ClassVar[str] = "example_portal"
    supported_actions: ClassVar[tuple[str, ...]] = (
        "ping",
        "login_check",
        "list_notices",
    )

    def health_check(self) -> SiteHealthStatus:
        t0 = time.monotonic()
        creds_ok = secrets_policy.credentials_present(self.name)
        session_ok = secrets_policy.session_state_present(self.name)
        probe = probe_launch()
        latency = int((time.monotonic() - t0) * 1000)

        state: Literal["healthy", "degraded", "unavailable", "unconfigured"]
        if not creds_ok and not session_ok:
            state = "unconfigured"
            warning = "자격증명/세션 파일 모두 없음 (정책 문서 참고)"
        elif not probe.available:
            state = "degraded"
            warning = probe.reason or "playwright 미설치"
        elif not session_ok:
            state = "degraded"
            warning = "세션 상태 파일 없음 → 최초 수동 로그인 필요"
        else:
            state = "healthy"
            warning = ""

        return SiteHealthStatus(
            site_name=self.name,
            connector_name=type(self).__name__,
            state=state,
            configured=creds_ok or session_ok,
            credentials_present=creds_ok,
            session_state_present=session_ok,
            browser_launch_ok=probe.available,
            login_check_status="session_only_check",
            latency_ms=latency,
            warning=warning,
            details={
                # 민감 경로 원문은 노출하지 않되, "어느 위치 정책을 썼는지" 수준만 남김.
                "credentials_policy": "secrets/sites/<site>.env",
                "session_policy": "secrets/browser_state/<site>.json",
            },
        )
