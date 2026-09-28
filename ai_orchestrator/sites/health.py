"""SiteHealthService.

- 전체/단일 사이트 health check 실행
- 결과를 dict 로 직렬화해 응답
- 안전한 읽기성 점검만 수행한다 (제출/수정/삭제 금지)

저장(snapshot) 은 이번 단계에서는 최소한 훅만 열어둔다.
"""

from __future__ import annotations

import logging
import time

from . import registry
from .connector import ConnectorError
from .models import SiteHealthStatus

logger = logging.getLogger(__name__)


class SiteHealthService:
    def list_connectors(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "class": type(c).__name__,
                "actions": list(c.supported_actions),
            }
            for c in registry.all_connectors()
        ]

    def check_one(self, site_name: str) -> SiteHealthStatus | None:
        conn = registry.get(site_name)
        if conn is None:
            return None
        return self._safe_health_check(site_name, conn)

    def check_all(self) -> list[SiteHealthStatus]:
        results: list[SiteHealthStatus] = []
        for conn in registry.all_connectors():
            results.append(self._safe_health_check(conn.name, conn))
        return results

    def _safe_health_check(self, site_name: str, conn) -> SiteHealthStatus:
        t0 = time.monotonic()
        try:
            status = conn.health_check()
            # connector 구현 측 오류로 latency 가 0인 경우 보정
            if not status.latency_ms:
                status.latency_ms = int((time.monotonic() - t0) * 1000)
            return status
        except ConnectorError as e:
            return SiteHealthStatus(
                site_name=site_name,
                connector_name=type(conn).__name__,
                state="unavailable",
                error=e.code,
                warning=e.message or "",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001 - 사이트 커넥터 health_check 실패를 캡처해 state=unavailable 로 안전하게 폴백(민감 원문 대신 예외 타입만 로깅) - 헬스체크는 읽기전용 상태조회이며 실패를 정상으로 위장하지 않음
            # 민감 원문이 섞이지 않게 타입 + 요약만 남긴다.
            logger.warning("health_check 실패: site=%s err=%s", site_name, type(e).__name__)
            return SiteHealthStatus(
                site_name=site_name,
                connector_name=type(conn).__name__,
                state="unavailable",
                error="HEALTH_CHECK_EXCEPTION",
                warning=type(e).__name__,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )


__all__ = ["SiteHealthService"]
