from __future__ import annotations

import os
import ssl
import urllib.request
from typing import Any
from urllib.parse import urlparse

BYPASS_HOSTS = frozenset({"haehan-ai.kr"})
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def host_needs_direct(server_url: str) -> bool:
    host = (urlparse(server_url).hostname or "").lower()
    return host in BYPASS_HOSTS


def extend_no_proxy(value: str | None = None) -> str:
    existing = [part.strip() for part in (value if value is not None else os.environ.get("NO_PROXY", "")).split(",")]
    merged = [part for part in existing if part]
    for host in sorted(BYPASS_HOSTS):
        if host not in merged:
            merged.append(host)
    return ",".join(merged)


def direct_child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["NO_PROXY"] = extend_no_proxy(env.get("NO_PROXY"))
    env["no_proxy"] = extend_no_proxy(env.get("no_proxy"))
    for key in _PROXY_ENV_KEYS:
        env.pop(key, None)
    return env


def urlopen_direct(req, *, timeout: float, context: ssl.SSLContext | None = None):
    handlers = [urllib.request.ProxyHandler({})]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)
    return opener.open(req, timeout=timeout)


def urlopen_for_server(server_url: str, req, *, timeout: float, context: ssl.SSLContext | None = None):
    if host_needs_direct(server_url):
        return urlopen_direct(req, timeout=timeout, context=context)
    return urllib.request.urlopen(req, timeout=timeout, context=context)


def websocket_connect_kwargs(server_url: str) -> dict[str, Any]:
    if host_needs_direct(server_url):
        return {"proxy": None}
    return {}
