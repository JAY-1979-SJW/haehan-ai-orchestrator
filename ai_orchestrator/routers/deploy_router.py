"""GitHub Webhook 수신 → 서버 자동 배포 엔드포인트 (L8).

엔드포인트:
  POST /api/v1/deploy/webhook   — GitHub push 이벤트 수신 → 배포 트리거
  GET  /api/v1/deploy/status    — 마지막 배포 결과 조회

보안 원칙:
  - HMAC-SHA256 서명 검증 (DEPLOY_WEBHOOK_SECRET). 실패 시 401.
  - secret 값 로그/응답 노출 금지.
  - 배포는 기존 deploy_api_with_runtime_gates.py 그대로 실행 (게이트 보존).
  - owner role 만 /deploy/status 접근 가능.
  - 동시 배포 방지: 실행 중이면 409 반환.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status

from ..auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deploy", tags=["deploy"])

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "ops" / "deploy_api_with_runtime_gates.py"
STATUS_FILE = ROOT / "data" / "runtime" / "deploy_api_with_runtime_gates_latest.json"

_lock = threading.Lock()
_running = False


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


def _run_deploy() -> None:
    global _running
    try:
        logger.info("deploy_webhook: starting deploy")
        subprocess.run(
            [sys.executable, str(DEPLOY_SCRIPT), "--approved"],
            cwd=str(ROOT),
            timeout=900,
            check=False,
        )
        logger.info("deploy_webhook: deploy finished")
    except Exception as exc:
        logger.error("deploy_webhook: error: %s", exc)
    finally:
        with _lock:
            _running = False


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """GitHub push 이벤트를 수신하여 배포를 트리거한다."""
    global _running

    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    if x_github_event != "push":
        return {"accepted": False, "reason": f"event_ignored:{x_github_event}"}

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    ref = payload.get("ref", "")
    if ref != "refs/heads/master":
        return {"accepted": False, "reason": f"branch_ignored:{ref}"}

    with _lock:
        if _running:
            raise HTTPException(status_code=409, detail="deploy_already_running")
        _running = True

    background_tasks.add_task(_run_deploy)
    logger.info("deploy_webhook: accepted push ref=%s", ref)
    return {"accepted": True, "ref": ref, "secret_values_output": False}


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
            "running": _running,
            "secret_values_output": False,
        }
    except Exception:
        return {"ok": False, "status": "status_file_unreadable", "secret_values_output": False}
