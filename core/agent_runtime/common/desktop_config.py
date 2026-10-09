"""Desktop agent config persistence (~/.haehan_agent/config.json).

저장 허용 필드: server_url, agent_id, label, created_at, version.
저장 금지: device_token / registration_code / Authorization / password /
token_hash / code_hash / 모든 비밀 값.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from core.agent_runtime.common.redaction import SENSITIVE_KEYS

DEFAULT_CONFIG_PATH: Path = Path(
    os.getenv("HAEHAN_AGENT_DESKTOP_CONFIG", str(Path.home() / ".haehan_agent" / "config.json"))
)

_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "server_url",
        "agent_id",
        "label",
        "created_at",
        "version",
        "local_host",
        "local_port",
    }
)


@dataclass
class DesktopConfig:
    server_url: str = ""
    agent_id: str = ""
    label: str = ""
    created_at: str = ""
    version: str = ""
    local_host: str = ""  # 비어있으면 127.0.0.1 기본값 사용
    local_port: int = 0  # 0이면 8765 기본값 사용

    def is_complete(self) -> bool:
        return bool(self.server_url and self.agent_id)


def _strip_secrets(data: dict) -> dict:
    """저장 직전 방어선 — 비밀키가 들어오면 제거하고 allow-list만 통과."""
    return {k: v for k, v in data.items() if k in _ALLOWED_KEYS and k.lower() not in SENSITIVE_KEYS}


def load_config(path: Path | None = None) -> DesktopConfig:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        return DesktopConfig()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DesktopConfig()
    if not isinstance(raw, dict):
        return DesktopConfig()
    safe = _strip_secrets(raw)
    try:
        local_port = int(safe.get("local_port", 0))
    except (ValueError, TypeError):
        local_port = 0
    return DesktopConfig(
        server_url=str(safe.get("server_url", "")),
        agent_id=str(safe.get("agent_id", "")),
        label=str(safe.get("label", "")),
        created_at=str(safe.get("created_at", "")),
        version=str(safe.get("version", "")),
        local_host=str(safe.get("local_host", "")),
        local_port=local_port,
    )


def save_config(cfg: DesktopConfig, path: Path | None = None) -> Path:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    body = _strip_secrets(asdict(cfg))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    with contextlib.suppress(OSError):
        p.chmod(0o600)  # Windows ACL은 별도 안내
    return p


def clear_config(path: Path | None = None) -> bool:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if p.exists():
        try:
            p.unlink()
            return True
        except OSError:
            return False
    return False


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DesktopConfig",
    "clear_config",
    "load_config",
    "save_config",
]
