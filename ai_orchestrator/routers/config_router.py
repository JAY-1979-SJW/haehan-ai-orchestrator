"""config_router.py — 데스크톱 앱 환경변수 배포 + 로컬 재로딩

엔드포인트:
  GET  /api/v1/config/desktop-env   — 원격 서버: 라이선스 인증 후 데스크톱용 env 반환
  POST /api/v1/config/reload        — 로컬 FastAPI: env dict 수신 후 os.environ 갱신

보안:
  - desktop-env: x-license-key 헤더 검증 (라이선스 DB)
  - reload: 127.0.0.1 전용 (로컬 Electron만 호출 가능)

L8 Server API 계층. 업무 로직 없음.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from ai_orchestrator.connectors.smartstore.license import verify as verify_license

logger = logging.getLogger(__name__)

config_router = APIRouter(prefix="/config", tags=["config"])

# 데스크톱 앱에 배포할 환경변수 키 목록 (값이 있는 것만 포함)
_DESKTOP_ENV_KEYS: list[str] = [
    "NAVER_OPENAPI_CLIENT_ID",
    "NAVER_OPENAPI_CLIENT_SECRET",
    "YOUTUBE_DATA_API_KEY",
    "YOUTUBE_CLIENT_SECRETS_FILE",
    "YOUTUBE_OAUTH_TOKEN_FILE",
    "YOUTUBE_OAUTH_REDIRECT_URI",
    "YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED",
    "GMAIL_CREDENTIALS_PATH",
    "GMAIL_TOKEN_PATH",
    "JWT_SECRET",
    "HTTP_USERS_PATH",
    "AUTH_ENABLED",
]


@config_router.get("/desktop-env")
async def get_desktop_env(x_license_key: str = Header(alias="x-license-key", default="")):
    """라이선스 키 인증 후 데스크톱용 환경변수 반환.

    원격 서버(haehan-ai.kr)에서만 의미 있는 엔드포인트.
    반환값은 HTTPS 전송되며 민감 값을 포함하므로 로그 출력 금지.
    """
    if not x_license_key:
        raise HTTPException(status_code=401, detail="x-license-key 헤더 필요")

    ok, _rec, reason = verify_license(x_license_key)
    if not ok:
        raise HTTPException(status_code=401, detail=f"라이선스 검증 실패: {reason}")

    env: dict[str, str] = {}
    for key in _DESKTOP_ENV_KEYS:
        val = os.environ.get(key, "")
        if val:
            env[key] = val

    logger.info("desktop-env 요청 — 키 %d개 반환 (license=...%s)", len(env), x_license_key[-6:])
    return {"ok": True, "env": env}


class ReloadRequest(BaseModel):
    env: dict[str, Any]


@config_router.post("/reload")
async def reload_config(body: ReloadRequest, request: Request):
    """로컬 Electron이 보낸 env dict를 os.environ에 적용.

    127.0.0.1 전용 — 외부에서 호출 불가.
    """
    client_ip = request.client.host if request.client else ""
    if client_ip not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="로컬 전용 엔드포인트")

    applied = 0
    for key, val in body.env.items():
        if key and isinstance(val, str) and val:
            os.environ[key] = val
            applied += 1

    logger.info("config reload — %d개 환경변수 적용 (from %s)", applied, client_ip)
    return {"ok": True, "applied": applied}
