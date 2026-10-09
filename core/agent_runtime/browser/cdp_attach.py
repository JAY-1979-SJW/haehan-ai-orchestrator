"""Safe local CDP attach discovery helpers.

This module is intentionally read-only. It validates a loopback-only Chrome
DevTools endpoint and summarizes version/tab payloads without exposing raw
debugger websocket URLs, query strings, fragments, or credentials.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
SAFE_VERSION_FIELDS = ("Browser", "Protocol-Version")


class CDPAttachValidationError(ValueError):
    """Raised when a CDP endpoint is outside the local attach boundary."""


@dataclass(frozen=True)
class CDPEndpoint:
    host: str = DEFAULT_CDP_HOST
    port: int = DEFAULT_CDP_PORT

    @property
    def base_url(self) -> str:
        host = "[::1]" if self.host == "::1" else self.host
        return f"http://{host}:{self.port}"

    @property
    def version_url(self) -> str:
        return f"{self.base_url}/json/version"

    @property
    def tabs_url(self) -> str:
        return f"{self.base_url}/json/list"


def normalize_cdp_endpoint(host: str = DEFAULT_CDP_HOST, port: int | str = DEFAULT_CDP_PORT) -> CDPEndpoint:
    normalized_host = str(host or "").strip().lower()
    if normalized_host not in LOOPBACK_HOSTS:
        raise CDPAttachValidationError("CDP host must be loopback")

    try:
        normalized_port = int(port)
    except (TypeError, ValueError) as exc:
        raise CDPAttachValidationError("CDP port must be an integer") from exc
    if not 1 <= normalized_port <= 65535:
        raise CDPAttachValidationError("CDP port is out of range")

    if normalized_host == "[::1]":
        normalized_host = "::1"
    return CDPEndpoint(host=normalized_host, port=normalized_port)


def build_cdp_version_url(host: str = DEFAULT_CDP_HOST, port: int | str = DEFAULT_CDP_PORT) -> str:
    return normalize_cdp_endpoint(host, port).version_url


def build_cdp_list_url(host: str = DEFAULT_CDP_HOST, port: int | str = DEFAULT_CDP_PORT) -> str:
    return normalize_cdp_endpoint(host, port).tabs_url


def summarize_cdp_version(payload: dict[str, Any]) -> dict[str, str]:
    return {field: str(payload.get(field, ""))[:160] for field in SAFE_VERSION_FIELDS}


def _safe_url_summary(raw_url: Any) -> dict[str, Any]:
    text = str(raw_url or "")
    parsed = urllib.parse.urlsplit(text)
    username_or_password = bool(parsed.username or parsed.password)
    hostname = parsed.hostname or ""
    origin = ""
    if parsed.scheme in {"http", "https"} and hostname:
        netloc = hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        origin = f"{parsed.scheme}://{netloc}"
    elif parsed.scheme in {"about", "chrome", "devtools"}:
        origin = parsed.scheme

    return {
        "scheme": parsed.scheme[:32],
        "origin": origin[:200],
        "has_path": bool(parsed.path and parsed.path not in {"", "/"}),
        "has_query": bool(parsed.query),
        "has_fragment": bool(parsed.fragment),
        "has_credentials": username_or_password,
    }


def summarize_cdp_tabs(payload: list[Any]) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict) or row.get("type") != "page":
            continue
        pages.append(
            {
                "title": str(row.get("title", ""))[:120],
                "url": _safe_url_summary(row.get("url")),
            }
        )
    return {
        "tab_count": len(pages),
        "tabs": pages,
    }


def _fetch_json(url: str, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_cdp_endpoint(
    host: str = DEFAULT_CDP_HOST,
    port: int | str = DEFAULT_CDP_PORT,
    *,
    timeout: float = 2.0,
    fetch_json: Callable[[str, float], Any] = _fetch_json,
) -> dict[str, Any]:
    """Probe a local CDP endpoint and return redacted discovery data."""
    endpoint = normalize_cdp_endpoint(host, port)
    try:
        version_payload = fetch_json(endpoint.version_url, timeout)
        tabs_payload = fetch_json(endpoint.tabs_url, timeout)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "host": endpoint.host,
            "port": endpoint.port,
            "error": str(exc)[:200],
        }

    if not isinstance(version_payload, dict):
        version_payload = {}
    if not isinstance(tabs_payload, list):
        tabs_payload = []
    return {
        "available": True,
        "host": endpoint.host,
        "port": endpoint.port,
        "version": summarize_cdp_version(version_payload),
        "tabs": summarize_cdp_tabs(tabs_payload),
    }
