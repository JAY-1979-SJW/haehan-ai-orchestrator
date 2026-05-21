# -*- coding: utf-8 -*-
"""CAD bridge registry & status — desktop hub side.

CAD-DESKTOP-HUB-CAD-BRIDGE-REGISTRY-STATUS-01.

Desktop hub (haehan-ai-orchestrator) 가 sibling repo
`14. CAD 산출 프로그램_WORK / local_bridge` 의 상태를 조회하기 위한
설정/상태 모델. 본 단계는 status/registry 만 — start/stop/restart/
proxy 는 후속 lifecycle / proxy 트랙으로 분리.

정책:
- CAD repo production 모듈 직접 import 0건. cross-repo 경계는 HTTP
  호출(`http://127.0.0.1:{port}/openapi.json`) 로만 확인.
- AutoCAD COM / DB write / process kill / process start 0건.
- desktop hub 자체 (port 8765) 와 CAD bridge (기본 port 8766) 분리.
- 8001 사용 금지.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────

# desktop hub 가 점유하는 포트 (별 트랙 — 변경 금지)
DESKTOP_HUB_PORT = 8765

# CAD local_bridge 기본 포트 (충돌 회피용). 사용자 설정으로 override 가능
# 하지만 본 registry 의 default 는 8766. 절대 8765 아님.
DEFAULT_CAD_BRIDGE_PORT = 8766

# CAD local_bridge host 기본값 — loopback only
DEFAULT_CAD_BRIDGE_HOST = "127.0.0.1"

# 금지 포트 (정책)
FORBIDDEN_CAD_BRIDGE_PORTS = (8001,)

# Status 값
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_STOPPED = "STOPPED"
STATUS_RUNNING = "RUNNING"
STATUS_UNREACHABLE = "UNREACHABLE"
STATUS_UNKNOWN = "UNKNOWN"

ALL_STATUSES = (
    STATUS_NOT_CONFIGURED,
    STATUS_STOPPED,
    STATUS_RUNNING,
    STATUS_UNREACHABLE,
    STATUS_UNKNOWN,
)

# CAD local_bridge openapi 에 등장해야 하는 시그니처 경로 (식별용)
_CAD_BRIDGE_SIGNATURE_PATHS = (
    "/acad/arch-quantity-tab/build-cards",
    "/acad/inventory/analyze-drawing-inventory",
)

_HTTP_TIMEOUT_SECONDS = 2.0


# ──────────────────────────────────────────────
# 설정 / 상태 모델
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class CadBridgeConfig:
    """CAD bridge 설정 — 사용자 설정에서 주입 가능.

    이번 단계에서는 실제 실행하지 않으므로 path 가 None 이어도 됨
    (status 만 조회). path 검증은 lifecycle 트랙으로 분리.
    """
    host: str = DEFAULT_CAD_BRIDGE_HOST
    port: int = DEFAULT_CAD_BRIDGE_PORT
    cad_repo_path: Optional[str] = None  # lifecycle 트랙에서 사용

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def is_configured(self) -> bool:
        """status 조회를 시도할지 결정.

        port 가 금지 포트이거나 hub 와 같으면 NOT_CONFIGURED.
        """
        if self.port in FORBIDDEN_CAD_BRIDGE_PORTS:
            return False
        if self.port == DESKTOP_HUB_PORT:
            return False
        if not self.host:
            return False
        return True


@dataclass(frozen=True)
class CadBridgeStatus:
    """CAD bridge 상태 응답.

    fastapi route 가 직접 serialize 가능하도록 dataclass 형태로 노출.
    """
    status: str
    host: str
    port: int
    detail: Optional[str] = None
    signaturePathsPresent: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "host": self.host,
            "port": self.port,
            "detail": self.detail,
            "signaturePathsPresent": self.signaturePathsPresent,
        }


# ──────────────────────────────────────────────
# Status 조회
# ──────────────────────────────────────────────

def _safe_fetch_openapi(base_url: str, timeout: float = _HTTP_TIMEOUT_SECONDS):
    """openapi.json 을 안전하게 fetch — 실패 시 None 반환.

    예외를 호출자에게 전파하지 않는다 (desktop 서버 안정성 보호).
    """
    url = f"{base_url}/openapi.json"
    try:
        with urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode())
    except URLError:
        return None
    except (json.JSONDecodeError, ValueError):
        return None
    except Exception as exc:  # noqa: BLE001 — 안전 격리
        logger.debug("openapi fetch unexpected error: %s", exc)
        return None


def check_status(config: CadBridgeConfig) -> CadBridgeStatus:
    """CAD bridge 상태 조회.

    절대 process 를 start / stop / kill 하지 않는다. HTTP GET 만 시도.

    분류:
    - NOT_CONFIGURED : config.is_configured() == False
    - STOPPED        : connection refused (URLError) — 미기동
    - UNREACHABLE    : 200 응답이나 CAD bridge signature path 부재
                       (포트 다른 서비스 점유 등)
    - RUNNING        : 200 + signature path ≥ 1
    - UNKNOWN        : 그 외 예상치 못한 응답
    """
    if not config.is_configured():
        return CadBridgeStatus(
            status=STATUS_NOT_CONFIGURED,
            host=config.host,
            port=config.port,
            detail=(
                f"port={config.port} is forbidden or unset "
                "(check user settings)"
            ),
            signaturePathsPresent=0,
        )

    openapi = _safe_fetch_openapi(config.base_url())
    if openapi is None:
        return CadBridgeStatus(
            status=STATUS_STOPPED,
            host=config.host,
            port=config.port,
            detail="connection refused or no response",
            signaturePathsPresent=0,
        )

    paths = openapi.get("paths") or {}
    if not isinstance(paths, dict):
        return CadBridgeStatus(
            status=STATUS_UNKNOWN,
            host=config.host,
            port=config.port,
            detail="openapi paths not a dict",
            signaturePathsPresent=0,
        )

    present = sum(1 for p in _CAD_BRIDGE_SIGNATURE_PATHS if p in paths)
    if present >= 1:
        return CadBridgeStatus(
            status=STATUS_RUNNING,
            host=config.host,
            port=config.port,
            detail=f"{present}/{len(_CAD_BRIDGE_SIGNATURE_PATHS)} signature paths",
            signaturePathsPresent=present,
        )

    return CadBridgeStatus(
        status=STATUS_UNREACHABLE,
        host=config.host,
        port=config.port,
        detail=(
            f"port {config.port} responded but no CAD bridge signature path "
            f"(occupied by different service?)"
        ),
        signaturePathsPresent=0,
    )


# ──────────────────────────────────────────────
# 설정 로더 — user_settings 가 cad_bridge_path / cad_bridge_port 를
# 노출하지 않는 환경에서도 안전한 기본값 반환.
# ──────────────────────────────────────────────

def load_default_config() -> CadBridgeConfig:
    """user_settings.py 변경 없이 환경변수 / 기본값으로 config 로드.

    user_settings.py 가 cad_bridge_* 필드를 노출하면 후속 lifecycle
    트랙에서 그 경로로 교체. 본 트랙은 user_settings.py 무수정 유지.
    """
    import os
    host = os.environ.get("CAD_BRIDGE_HOST", DEFAULT_CAD_BRIDGE_HOST)
    try:
        port = int(os.environ.get("CAD_BRIDGE_PORT", DEFAULT_CAD_BRIDGE_PORT))
    except ValueError:
        port = DEFAULT_CAD_BRIDGE_PORT
    cad_repo_path = os.environ.get("CAD_REPO_PATH")
    return CadBridgeConfig(host=host, port=port, cad_repo_path=cad_repo_path)


__all__ = [
    "DESKTOP_HUB_PORT",
    "DEFAULT_CAD_BRIDGE_PORT",
    "DEFAULT_CAD_BRIDGE_HOST",
    "FORBIDDEN_CAD_BRIDGE_PORTS",
    "STATUS_NOT_CONFIGURED",
    "STATUS_STOPPED",
    "STATUS_RUNNING",
    "STATUS_UNREACHABLE",
    "STATUS_UNKNOWN",
    "ALL_STATUSES",
    "CadBridgeConfig",
    "CadBridgeStatus",
    "check_status",
    "load_default_config",
]
