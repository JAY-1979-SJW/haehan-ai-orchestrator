"""서버 관리 개요 엔드포인트 (L8) — 인스턴스 정보 + 라이브 헬스 + 배포 상태.

IXcloud 콘솔에서 하던 서버 상태 점검을 앱 안에서 보기 위한 read-only 집계 API.
- 비밀(키/비번)은 응답에 절대 포함하지 않는다.
- 방화벽 변경 등 쓰기 작업은 포함하지 않는다(콘솔 링크로 안내).
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from ai_orchestrator.paths.runtime import data_dir
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/server", tags=["server"])

ROOT = Path(__file__).resolve().parents[2]
_DEPLOY_STATUS_FILE = data_dir() / "runtime" / "server_deploy_latest.json"

# ── 인스턴스 정보 (IXcloud R2 / project haehan-ai) ────────────────────────────
INSTANCES: list[dict[str, Any]] = [
    {
        "hostname": "haehan-mcp",
        "role": "오케스트레이터 / MCP",
        "os": "Ubuntu 22.04",
        "flavor": "4Core 8GB",
        "os_volume": "50GB (Premium)",
        "user": "ubuntu",
        "public_ip": "1.201.176.236",
        "domains": ["app.haehan-ai.kr"],
        "check_ports": [443, 22, 8401, 8092],
    },
    {
        "hostname": "haehan-webdb",
        "role": "웹 / DB",
        "os": "Ubuntu 22.04",
        "flavor": "4Core 8GB",
        "os_volume": "50GB (Premium)",
        "user": "ubuntu",
        "public_ip": "1.201.177.67",
        "domains": ["haehan-ai.kr"],
        "check_ports": [443, 22],
    },
]

PORT_LABELS = {22: "SSH", 80: "HTTP", 443: "HTTPS", 8401: "API", 8092: "릴레이"}

LINKS = {
    "console": "https://console.ixcloud.net",
    "security_group_manual": "https://manual.kinx.net/ixcloud/ixcloud/network/access_and_security",
    "monitoring_manual": "https://manual.kinx.net/ixcloud/ixcloud/monitoring/monitoring_system_guide",
}

HEALTH_URLS = [
    ("app.haehan-ai.kr", "https://app.haehan-ai.kr/"),
    ("haehan-ai.kr", "https://haehan-ai.kr/"),
]


def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as exc:  # noqa: BLE001 - 서버 상태 read-only 집계 API(문서에 '비밀 응답에 포함 안 함', '쓰기 작업 없음' 명시) — TCP 포트체크/HTTP헬스체크/배포상태읽기 실패 시 모두 False/None/unavailable로 안전 폴백.
        logger.debug("TCP 포트 확인 실패: %s", type(exc).__name__)
        return False


def _http_status(url: str, timeout: float = 6.0) -> int | None:
    """리다이렉트 따라가지 않고 첫 응답 상태코드 반환(도달성 판단용)."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # type: ignore[override]
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, method="GET"), timeout=timeout) as r:  # noqa: S310
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as exc:  # noqa: BLE001 - 서버 상태 read-only 집계 API(문서에 '비밀 응답에 포함 안 함', '쓰기 작업 없음' 명시) — TCP 포트체크/HTTP헬스체크/배포상태읽기 실패 시 모두 False/None/unavailable로 안전 폴백.
        logger.debug("HTTP 상태 확인 실패: %s", type(exc).__name__)
        return None


def _read_deploy_status() -> dict[str, Any]:
    if not _DEPLOY_STATUS_FILE.exists():
        return {"available": False, "status": "no_deploy_run_yet"}
    try:
        d = json.loads(_DEPLOY_STATUS_FILE.read_text(encoding="utf-8"))
        return {
            "available": True,
            "ok": d.get("ok"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "service": d.get("service"),
        }
    except Exception as exc:  # noqa: BLE001 - 서버 상태 read-only 집계 API(문서에 '비밀 응답에 포함 안 함', '쓰기 작업 없음' 명시) — TCP 포트체크/HTTP헬스체크/배포상태읽기 실패 시 모두 False/None/unavailable로 안전 폴백.
        logger.warning("배포 상태 파일 읽기 실패: %s", type(exc).__name__)
        return {"available": False, "status": "status_file_unreadable"}


@router.get("/overview")
def server_overview(user: dict = Depends(require_role("admin", "owner"))) -> dict[str, Any]:
    """서버 인스턴스 + 라이브 헬스 + 배포 상태 집계."""
    instances = []
    for inst in INSTANCES:
        ip = inst["public_ip"]
        ports = {
            str(p): {
                "label": PORT_LABELS.get(p, str(p)),
                "open": _tcp_open(ip, p),
            }
            for p in inst["check_ports"]
        }
        instances.append({**inst, "ports": ports})

    health = [{"name": name, "url": url, "status": _http_status(url)} for name, url in HEALTH_URLS]

    return {
        "ok": True,
        "zone": "R2",
        "project": "haehan-ai",
        "instances": instances,
        "health": health,
        "deploy": _read_deploy_status(),
        "links": LINKS,
        "note": "보안그룹(방화벽) 변경은 IXcloud 콘솔에서 수행하세요. SSH 22번이 닫혀 있으면 배포가 차단됩니다.",
    }
