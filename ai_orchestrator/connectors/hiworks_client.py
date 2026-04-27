"""Hiworks 공식 API HTTP 클라이언트 래퍼.

설계 원칙:
- 비공식 스크래핑 금지. 반드시 공식 OpenAPI / REST 엔드포인트만 호출한다.
- 자격증명은 hiworks_config 에서 받아오고, 헤더 외 외부에 노출하지 않는다.
- dry_run 모드에서는 어떤 네트워크 호출도 발생시키지 않는다.
- 응답은 ``HiworksResponse`` 로 표준화 (status / data / error_code).
- 로그에는 method/path/status 만 남기고 토큰/응답 본문 원문은 남기지 않는다.

이번 단계는 "골격" 이 목표. 실제 엔드포인트 매핑은 공식 앱 등록/문서 확인 뒤
hiworks_collectors 에서 path 만 바꾸면 되도록 generic 한 ``request()`` 만 둔다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from . import hiworks_config

logger = logging.getLogger(__name__)


# Hiworks 응답 표준 스키마. status="dry_run" 인 경우 외부 호출이 발생하지 않음.
ResponseStatus = str  # "ok" | "dry_run" | "error" | "unconfigured"


@dataclass
class HiworksResponse:
    status: ResponseStatus
    http_status: Optional[int] = None
    data: Any = None
    error_code: str = ""
    error_message: str = ""
    request_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "http_status": self.http_status,
            "data": self.data,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "request_summary": self.request_summary,
        }


class HiworksClient:
    """Hiworks REST 호출을 위한 얇은 래퍼.

    - ``dry_run=True`` (config 또는 호출 단위 override) 면 네트워크를 타지 않는다.
    - ``transport`` 인자로 httpx-like 콜러블을 주입할 수 있어 테스트 용이.
        signature: ``transport(method, url, headers, params, json) -> (status, json_or_text)``
    """

    def __init__(
        self,
        config: Optional[hiworks_config.HiworksConfig] = None,
        transport: Optional[Any] = None,
    ):
        self._config = config or hiworks_config.load_config()
        self._transport = transport

    @property
    def config(self) -> hiworks_config.HiworksConfig:
        return self._config

    # ── 헤더 ────────────────────────────────────────────────────────
    def build_auth_headers(self) -> dict:
        """공식 API 호출용 헤더. 값은 노출하지 않고 키만 로그에 남기는 것을 권장.

        Hiworks 공식 문서 확인 전이므로 일반적인 OAuth Bearer 형태를 가정한다.
        실제 값은 앱 등록 후 토큰 발급 절차에 맞춰 교체.
        """
        return {
            "Authorization": f"Bearer {self._config.office_token}",
            "X-Client-Id": self._config.client_id,
            "Accept": "application/json",
            "User-Agent": "haehan-ai-orchestrator/hiworks-client (read-only)",
        }

    # ── URL 빌더 ────────────────────────────────────────────────────
    def build_url(self, path: str) -> str:
        base = self._config.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    # ── 요청 ────────────────────────────────────────────────────────
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        dry_run: Optional[bool] = None,
    ) -> HiworksResponse:
        """공통 요청 래퍼.

        - dry_run override 가 None 이면 config.dry_run 을 따른다.
        - method 는 GET 권장 (이번 단계는 읽기 전용). 그 외는 차단.
        """
        method_u = method.upper()
        # 1단계 안전장치 — 상태 변경 메서드는 명시적으로 차단.
        if method_u not in {"GET"}:
            return HiworksResponse(
                status="error",
                error_code="METHOD_NOT_ALLOWED_IN_PHASE_1",
                error_message=f"method={method_u} 는 1단계에서 허용되지 않음 (read-only)",
                request_summary={"method": method_u, "path": path},
            )

        url = self.build_url(path)
        summary = {
            "method": method_u,
            "path": path,
            # 토큰/시크릿은 절대 포함하지 않는다.
            "header_keys": sorted(self.build_auth_headers().keys()),
            "param_keys": sorted((params or {}).keys()),
        }

        effective_dry_run = self._config.dry_run if dry_run is None else dry_run
        if effective_dry_run:
            logger.info(
                "[HIWORKS-DRY-RUN] method=%s path=%s param_keys=%s",
                method_u, path, summary["param_keys"],
            )
            return HiworksResponse(
                status="dry_run",
                http_status=None,
                data={"note": "dry_run — 실제 호출 미수행", "url": url},
                request_summary=summary,
            )

        # live 호출 직전 검증
        try:
            hiworks_config.require_live(self._config)
        except hiworks_config.HiworksConfigError as e:
            logger.warning("[HIWORKS-UNCONFIGURED] %s", str(e))
            return HiworksResponse(
                status="unconfigured",
                error_code="MISSING_CREDENTIALS",
                error_message=str(e),
                request_summary=summary,
            )

        if self._transport is None:
            return HiworksResponse(
                status="error",
                error_code="TRANSPORT_NOT_WIRED",
                error_message="실제 HTTP 전송 계층 미연결 — 공식 앱 승인 후 연결 예정",
                request_summary=summary,
            )

        try:
            http_status, body = self._transport(
                method=method_u,
                url=url,
                headers=self.build_auth_headers(),
                params=params or {},
                json=json,
            )
        except Exception as e:  # noqa: BLE001
            # 예외 메시지에 요청 본문/시크릿이 섞일 가능성 — 타입만 노출.
            logger.exception("[HIWORKS-TRANSPORT-ERROR] type=%s", type(e).__name__)
            return HiworksResponse(
                status="error",
                error_code="TRANSPORT_EXCEPTION",
                error_message=type(e).__name__,
                request_summary=summary,
            )

        if 200 <= int(http_status) < 300:
            return HiworksResponse(
                status="ok",
                http_status=int(http_status),
                data=body,
                request_summary=summary,
            )
        return HiworksResponse(
            status="error",
            http_status=int(http_status),
            error_code=f"HTTP_{http_status}",
            error_message="non-2xx response",
            request_summary=summary,
        )


__all__ = ["HiworksClient", "HiworksResponse"]
