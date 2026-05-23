"""Boundary adapter for desktop runtime dependencies in ``local_agent``.

Desktop entry points should depend on this module instead of importing token,
registration, diagnostics, or websocket implementations directly. Keeping the
imports here makes the runtime boundary auditable and easier to gate.
"""
from __future__ import annotations

from typing import Any


def load_desktop_config() -> Any:
    from local_agent.desktop_config import load_config

    return load_config()


def build_desktop_config(
    *,
    server_url: str,
    agent_id: str,
    label: str = "",
    created_at: str = "",
    version: str = "",
) -> Any:
    from local_agent.desktop_config import DesktopConfig

    return DesktopConfig(
        server_url=server_url,
        agent_id=agent_id,
        label=label,
        created_at=created_at,
        version=version,
    )


def save_desktop_config(config: Any) -> Any:
    from local_agent.desktop_config import save_config

    return save_config(config)


def check_device_token(
    server_url: str,
    agent_id: str,
    *,
    allow_plaintext_fallback: bool = False,
) -> tuple[bool, str]:
    from local_agent.token_store import has_device_token, keyring_backend_name

    present = has_device_token(
        server_url,
        agent_id,
        allow_plaintext_fallback=allow_plaintext_fallback,
    )
    return bool(present), keyring_backend_name()


def has_any_token() -> bool:
    from local_agent import token_store

    return bool(getattr(token_store, "has_token", lambda: False)())


def save_device_token(
    server_url: str,
    agent_id: str,
    device_token: str,
    *,
    allow_plaintext_fallback: bool = False,
) -> str:
    from local_agent.token_store import save_device_token as _save_device_token

    return _save_device_token(
        server_url,
        agent_id,
        device_token,
        allow_plaintext_fallback=allow_plaintext_fallback,
    )


def load_device_token(server_url: str, agent_id: str) -> str:
    from local_agent.token_store import load_device_token as _load_device_token

    return _load_device_token(server_url, agent_id) or ""


def normalize_ws_url(server_url: str) -> str:
    from local_agent.connection_diagnostics import normalize_ws_url as _normalize_ws_url

    return _normalize_ws_url(server_url)


def build_diagnostics(**kwargs: Any) -> Any:
    from local_agent.connection_diagnostics import build_diagnostics as _build_diagnostics

    return _build_diagnostics(**kwargs)


def mask_agent_id(agent_id: str) -> str:
    from local_agent.connection_diagnostics import mask_agent_id as _mask_agent_id

    return _mask_agent_id(agent_id)


def register_with_code(**kwargs: Any) -> Any:
    from local_agent.registration_client import register_with_code as _register_with_code

    return _register_with_code(**kwargs)


def run_websocket_client(*, server_url: str, agent_id: str, device_token: str) -> Any:
    from local_agent import config
    from local_agent.websocket_client import connect

    config.SERVER_BASE_URL = server_url
    config.WEBSOCKET_ENABLED = True
    return connect(agent_id, device_token)
