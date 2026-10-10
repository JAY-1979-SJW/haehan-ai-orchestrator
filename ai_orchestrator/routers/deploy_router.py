"""GitHub Webhook 수신 → 서버 자동 배포 엔드포인트 (L8).

엔드포인트:
  POST /api/v1/deploy/webhook   — GitHub push 이벤트 수신 → 배포 트리거
  GET  /api/v1/deploy/status    — 마지막 배포 결과 조회

보안 원칙:
  - HMAC-SHA256 서명 검증 (DEPLOY_WEBHOOK_SECRET). 실패 시 401.
  - secret 값 로그/응답 노출 금지.
  - 배포는 tools/server_deploy.py 로 위임 (서버 전용, docker 보호됨).
  - owner role 만 /deploy/status 접근 가능.
  - 동시 배포 방지: 실행 중이면 409 반환.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ai_orchestrator.paths.runtime import data_dir
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deploy", tags=["deploy"])

ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = data_dir() / "runtime" / "server_deploy_latest.json"
# 호스트 트리거 데몬 주소 (host.docker.internal:8401)
TRIGGER_HOST = os.environ.get("DEPLOY_TRIGGER_HOST", "host.docker.internal")
TRIGGER_PORT = int(os.environ.get("DEPLOY_TRIGGER_PORT", "8401"))
TRIGGER_URL = f"http://{TRIGGER_HOST}:{TRIGGER_PORT}/trigger"


def _webhook_secret() -> bytes:
    secret = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="deploy_webhook_not_configured")
    return secret.encode()


def _verify_signature(body: bytes, sig_header: str | None) -> None:
    if not sig_header or not sig_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="missing_signature")
    expected = "sha256=" + hmac.new(_webhook_secret(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=401, detail="invalid_signature")


def _forward_to_daemon(body: bytes) -> dict[str, Any]:
    """호스트 배포 트리거 엔드포인트로 webhook 전달."""
    secret = os.environ.get("DEPLOY_WEBHOOK_SECRET", "").encode()
    sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        TRIGGER_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Deploy-Signature": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        if e.code == 409:
            raise HTTPException(status_code=409, detail="deploy_already_running") from e
        raise HTTPException(status_code=502, detail=f"trigger_daemon_error:{e.code}:{detail}") from e
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"trigger_daemon_unreachable:{exc}") from exc


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """GitHub push 이벤트를 수신하여 호스트 배포 데몬으로 트리거를 전달한다."""
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    if x_github_event != "push":
        return {"accepted": False, "reason": f"event_ignored:{x_github_event}"}

    try:
        payload = json.loads(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc

    ref = payload.get("ref", "")
    if ref != "refs/heads/master":
        return {"accepted": False, "reason": f"branch_ignored:{ref}"}

    result = _forward_to_daemon(body)
    logger.info("deploy_webhook: forwarded to daemon ref=%s result=%s", ref, result)
    return {"accepted": True, "ref": ref, "daemon": result, "secret_values_output": False}


@router.get("/status")
def deploy_status(user: dict = Depends(require_role("owner"))) -> dict[str, Any]:
    """마지막 배포 결과를 반환한다 (owner 전용)."""
    if not STATUS_FILE.exists():
        return {"ok": None, "status": "no_deploy_run_yet", "secret_values_output": False}
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return {
            "ok": data.get("ok"),
            "status": data.get("status"),
            "created_at": data.get("created_at"),
            "service": data.get("service"),
            "running": False,
            "secret_values_output": False,
        }
    except Exception as err:  # noqa: BLE001 - GitHub Webhook 배포 트리거(문서에 'HMAC-SHA256 서명 검증 실패시 401' 명시) — 서명검증은 except와 무관한 명시적 hmac.compare_digest 로직이며, except는 데몬 연결실패/JSON파싱실패/상태파일 읽기실패를 각각 HTTPException 또는 명확한 실패 dict로 반환.
        logger.warning("배포 상태 읽기 실패: %s", type(err).__name__)
        return {"ok": False, "status": "status_file_unreadable", "secret_values_output": False}
