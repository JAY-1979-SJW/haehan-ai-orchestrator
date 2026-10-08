"""DummyConnector.

외부 의존 없이 구조 검증용으로만 동작한다.
- health_check 는 항상 "healthy" 를 반환 (단, 브라우저 기동 가능 여부는 참고만 기록)
- dry_run 은 입력 task 요약만 반환
- execute 는 NOT_IMPLEMENTED
"""
from __future__ import annotations

import time
from typing import ClassVar

from .browser import probe_launch
from .connector import SiteConnector
from .models import SiteHealthStatus


class DummyConnector(SiteConnector):
    name: ClassVar[str] = "dummy"
    supported_actions: ClassVar[tuple[str, ...]] = ("ping", "describe")

    def health_check(self) -> SiteHealthStatus:
        t0 = time.monotonic()
        probe = probe_launch()
        latency = int((time.monotonic() - t0) * 1000)
        return SiteHealthStatus(
            site_name=self.name,
            connector_name=type(self).__name__,
            state="healthy",
            configured=True,
            credentials_present=False,  # dummy 는 자격증명 불필요
            session_state_present=False,
            browser_launch_ok=probe.available,
            login_check_status="not_required",
            latency_ms=latency,
            warning="" if probe.available else "playwright 미설치(선택 의존성)",
            details={"purpose": "structure_smoke_test"},
        )
