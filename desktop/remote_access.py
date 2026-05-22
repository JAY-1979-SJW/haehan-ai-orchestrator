"""원격 접속 설정 및 액세스 토큰 관리.

원격 접속 활성화 시:
- LOCAL_HOST → 0.0.0.0 으로 바인딩 (모든 인터페이스)
- 비 localhost 요청에 Bearer 토큰 검증 필수
- 토큰은 ~/.haehan_agent/remote_token 에 저장 (chmod 600)
- 토큰 출력/로깅 금지 (마스킹만 허용)

보안 원칙:
- 토큰 값 로그 출력 금지
- 원격 제어 허용 명령 화이트리스트만 실행
- 비가역 작업(파일 삭제, DB write, 배포) 원격 실행 금지
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import socket
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TOKEN_PATH = Path(
    os.getenv("HAEHAN_AGENT_DESKTOP_CONFIG",
              str(Path.home() / ".haehan_agent" / "config.json"))
).parent / "remote_token"

_STATE_PATH = Path(
    os.getenv("HAEHAN_AGENT_DESKTOP_CONFIG",
              str(Path.home() / ".haehan_agent" / "config.json"))
).parent / "remote_access_state.json"

# 원격 제어 허용 명령 화이트리스트
ALLOWED_REMOTE_COMMANDS: frozenset[str] = frozenset({
    "get_status",
    "get_screenshot",
    "open_url",
    "get_logs_tail",
    "ping",
})


def _get_local_ip() -> str:
    """PC의 로컬 네트워크 IP 조회."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def is_enabled() -> bool:
    """원격 접속 활성화 여부."""
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        return bool(data.get("enabled", False))
    except Exception:
        return False


def enable() -> str:
    """원격 접속 활성화 + 토큰 생성(없으면). 토큰 반환."""
    token = _load_token() or _generate_token()
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        json.dumps({"enabled": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("remote access enabled (token masked)")
    return token


def disable() -> None:
    """원격 접속 비활성화 (토큰 보존)."""
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        json.dumps({"enabled": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("remote access disabled")


def _generate_token() -> str:
    token = secrets.token_urlsafe(32)
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(token, encoding="utf-8")
    try:
        os.chmod(_TOKEN_PATH, 0o600)
    except OSError:
        pass
    return token


def _load_token() -> Optional[str]:
    try:
        return _TOKEN_PATH.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def get_token() -> Optional[str]:
    """저장된 토큰 반환. 없으면 None."""
    return _load_token()


def get_token_masked() -> str:
    """토큰 앞 6자리만 표시 (로그/UI 표시용)."""
    tok = _load_token()
    if not tok:
        return "(없음)"
    return tok[:6] + "…"


def get_access_url(port: int) -> str:
    """현재 PC IP + 포트 기반 접속 URL."""
    ip = _get_local_ip()
    return f"http://{ip}:{port}"


def rotate_token() -> str:
    """토큰 재발급."""
    token = _generate_token()
    logger.info("remote access token rotated")
    return token


def verify_token(provided: Optional[str]) -> bool:
    """제공된 토큰이 저장된 토큰과 일치하는지 검증."""
    stored = _load_token()
    if not stored or not provided:
        return False
    return secrets.compare_digest(stored.encode(), provided.encode())


__all__ = [
    "is_enabled", "enable", "disable",
    "get_token", "get_token_masked", "get_access_url",
    "rotate_token", "verify_token",
    "ALLOWED_REMOTE_COMMANDS",
]
