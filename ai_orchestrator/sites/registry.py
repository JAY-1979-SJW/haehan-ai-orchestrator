"""사이트 커넥터 registry.

- 모듈 로드 시점에 기본 커넥터를 등록한다.
- 테스트/다른 런타임에서 register() / unregister() 로 동적 조작 가능.
- 이름은 커넥터 name 속성을 기준으로 한다.
"""

from __future__ import annotations

import logging
import threading

from .connector import SiteConnector

logger = logging.getLogger(__name__)

_registry: dict[str, SiteConnector] = {}
_lock = threading.Lock()


def register(connector: SiteConnector, *, overwrite: bool = False) -> None:
    if not isinstance(connector, SiteConnector):
        raise TypeError("connector must be a SiteConnector instance")
    name = connector.name
    if not name:
        raise ValueError("connector.name 비어있음")
    with _lock:
        if name in _registry and not overwrite:
            logger.debug("connector 이미 등록됨: %s (overwrite=False)", name)
            return
        _registry[name] = connector
        logger.info("connector 등록: %s", name)


def unregister(name: str) -> None:
    with _lock:
        _registry.pop(name, None)


def get(name: str) -> SiteConnector | None:
    with _lock:
        return _registry.get(name)


def all_connectors() -> list[SiteConnector]:
    with _lock:
        return list(_registry.values())


def all_names() -> list[str]:
    with _lock:
        return sorted(_registry.keys())


def clear() -> None:
    """테스트 전용. 프로덕션 경로에서는 호출하지 말 것."""
    with _lock:
        _registry.clear()


def _load_builtin() -> None:
    """기본 제공 샘플 커넥터를 등록한다."""
    from .dummy import DummyConnector
    from .example_portal import ExamplePortalConnector

    for conn in (DummyConnector(), ExamplePortalConnector()):
        register(conn)


# 모듈 로드 시 1회 초기화 (멱등)
_load_builtin()


__all__ = [
    "all_connectors",
    "all_names",
    "clear",
    "get",
    "register",
    "unregister",
]
