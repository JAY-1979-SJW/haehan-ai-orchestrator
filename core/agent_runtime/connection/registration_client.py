"""register-with-code 교환 client.

POST {server}/api/v1/local-agents/register-with-code

Basic Auth를 사용하지 않는다. registration_code는 메모리 변수로만 흐르고
응답에서 받은 device_token도 호출자가 즉시 keyring에 저장한 뒤 폐기해야 한다.
이 모듈은 device_token / registration_code 평문을 어떤 로그에도 남기지 않는다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib import error as _urlerr
from urllib import request as _urlreq

from core.agent_runtime.connection import network_bypass as _network_bypass

logger = logging.getLogger(__name__)


class RegistrationError(RuntimeError):
    """register-with-code 실패 (네트워크/HTTP/응답 형식)."""

    def __init__(self, *, http_status: int | None = None, generic_message: str = "registration failed"):
        super().__init__(generic_message)
        self.http_status = http_status
        self.generic_message = generic_message


@dataclass
class RegistrationResult:
    agent_id: str
    code_id: str
    host: str
    os_name: str
    version: str
    registered_at: str
    label: str
    allowed_actions: list[str]


def _build_url(server_url: str) -> str:
    base = server_url.rstrip("/")
    return f"{base}/api/v1/local-agents/register-with-code"


def register_with_code(
    server_url: str,
    registration_code: str,
    *,
    host: str,
    os_name: str,
    version: str,
    timeout: float = 10.0,
    _opener=None,
) -> tuple[RegistrationResult, str]:
    """등록 교환을 수행하고 (메타데이터, device_token) 을 반환.

    호출자는 device_token을 즉시 token_store에 저장한 뒤 변수 참조를 끊어야 한다.
    실패 시 RegistrationError. 메시지는 generic — 응답 본문/원문 미노출.
    """
    if not server_url:
        raise RegistrationError(generic_message="server_url is required")
    if not registration_code:
        raise RegistrationError(generic_message="registration_code is required")

    url = _build_url(server_url)
    body = json.dumps(
        {
            "registration_code": registration_code,
            "host": host or "",
            "os_name": os_name or "",
            "version": version or "0.1.0",
        }
    ).encode("utf-8")
    # URL 은 사용자가 설정한 서버 base URL + 고정 경로로만 조립된다(임의 스킴 입력 경로 없음)
    req = _urlreq.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})  # noqa: S310

    try:
        # 테스트용 _opener 는 (req, timeout=) 시그니처, 기본 경로는 (server_url, req, timeout=) 시그니처다.
        if _opener is None:
            response_ctx = _network_bypass.urlopen_for_server(server_url, req, timeout=timeout)
        else:
            response_ctx = _opener(req, timeout=timeout)
        with response_ctx as resp:
            raw = resp.read().decode("utf-8")
    except _urlerr.HTTPError as e:
        # 응답 body는 원칙적으로 출력하지 않는다. status만 generic 메시지에 포함.
        raise RegistrationError(
            http_status=e.code,
            generic_message="invalid_registration_code"
            if e.code in (400, 401, 403, 410)
            else f"registration_failed_http_{e.code}",
        ) from None
    except _urlerr.URLError as e:
        # 네트워크 단계 실패. 원문 메시지(internal)는 디버그 로그에 한해 짧게만.
        logger.debug("register_with_code URL error: %s", type(e).__name__)
        raise RegistrationError(generic_message="registration_network_error") from None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RegistrationError(generic_message="registration_invalid_response") from None
    if not isinstance(payload, dict):
        raise RegistrationError(generic_message="registration_invalid_response")

    device_token = str(payload.get("device_token") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    code_id = str(payload.get("code_id") or "").strip()
    if not (device_token and agent_id and code_id):
        raise RegistrationError(generic_message="registration_invalid_response")

    meta = RegistrationResult(
        agent_id=agent_id,
        code_id=code_id,
        host=str(payload.get("host") or ""),
        os_name=str(payload.get("os_name") or ""),
        version=str(payload.get("version") or ""),
        registered_at=str(payload.get("registered_at") or ""),
        label=str(payload.get("label") or ""),
        allowed_actions=list(payload.get("allowed_actions") or []),
    )
    return meta, device_token


__all__ = ["RegistrationError", "RegistrationResult", "register_with_code"]
