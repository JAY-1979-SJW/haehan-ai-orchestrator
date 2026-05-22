"""데스크탑 앱 로컬 서버 호스트/포트 설정 중앙화.

우선순위 (높음 → 낮음):
  1. 환경변수  HAEHAN_LOCAL_HOST / HAEHAN_LOCAL_PORT
  2. ~/.haehan_agent/config.json 의 local_host / local_port 필드
  3. 기본값 127.0.0.1 / 8765

사용법:
    from desktop.app_config import LOCAL_HOST, LOCAL_PORT, LOCAL_URL
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_CONFIG_PATH = Path(
    os.getenv("HAEHAN_AGENT_DESKTOP_CONFIG",
              str(Path.home() / ".haehan_agent" / "config.json"))
)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def _load_from_file() -> tuple[str, int]:
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        host = str(data.get("local_host", _DEFAULT_HOST)).strip() or _DEFAULT_HOST
        port = int(data.get("local_port", _DEFAULT_PORT))
        return host, port
    except Exception:
        return _DEFAULT_HOST, _DEFAULT_PORT


def _resolve() -> tuple[str, int]:
    file_host, file_port = _load_from_file()
    host = os.getenv("HAEHAN_LOCAL_HOST", file_host).strip() or _DEFAULT_HOST
    try:
        port = int(os.getenv("HAEHAN_LOCAL_PORT", str(file_port)))
    except ValueError:
        port = file_port
    return host, port


LOCAL_HOST, LOCAL_PORT = _resolve()
LOCAL_URL = f"http://{LOCAL_HOST}:{LOCAL_PORT}"

# new_shell이 공식 기본 UI — legacy UI 제거 완료 (HAEHAN-DESKTOP-LEGACY-UI-REMOVAL-01)
# HAEHAN_DESKTOP_UI 환경변수는 호환성을 위해 유지되나 legacy 값은 무시된다.
_UI_MODE = os.getenv("HAEHAN_DESKTOP_UI", "new_shell").strip().lower()
ACTIVE_SHELL_URL = f"{LOCAL_URL}/app-new"  # legacy UI 제거 — 항상 /app-new 사용


def effective_bind_host() -> str:
    """원격 접속 활성화 시 0.0.0.0, 아니면 LOCAL_HOST."""
    try:
        from desktop.remote_access import is_enabled
        return "0.0.0.0" if is_enabled() else LOCAL_HOST
    except Exception:
        return LOCAL_HOST


__all__ = ["LOCAL_HOST", "LOCAL_PORT", "LOCAL_URL", "ACTIVE_SHELL_URL", "effective_bind_host"]
