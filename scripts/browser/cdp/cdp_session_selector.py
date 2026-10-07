"""CDP session discovery and selection for parallel browser work.

The selector never launches or restarts a browser. It only inspects reachable
CDP endpoints and chooses a session that matches the requested work domain
without crossing into another active work domain.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORTS = (9222, 9223, 9333, 9444, 9555)

JsonFetcher = Callable[[str, float], Any]


@dataclass(frozen=True)
class CdpCandidate:
    port: int
    available: bool
    tabs: list[dict[str, str]]
    error: str = ""


def configured_ports(value: str | None = None) -> list[int]:
    raw = value if value is not None else os.environ.get("CDP_DISCOVERY_PORTS", "")
    if not raw.strip():
        return list(DEFAULT_PORTS)
    ports: list[int] = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            port = int(item)
        except ValueError:
            continue
        if 1 <= port <= 65535 and port not in ports:
            ports.append(port)
    return ports or list(DEFAULT_PORTS)


def _fetch_json(url: str, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:  # noqa: BLE001 - CDP 세션 후보 탐색 -- 도메인 추출 실패 시 빈 문자열, 후보 조회 실패는 unavailable로 기록(에러 메시지 180자로 절단)
        return ""


def _matches(domain: str, patterns: list[str]) -> bool:
    domain = domain.lower()
    return any(domain == item or domain.endswith("." + item) for item in patterns)


def discover_cdp_candidates(
    *,
    ports: list[int] | None = None,
    host: str = DEFAULT_HOST,
    timeout: float = 0.8,
    fetch_json: JsonFetcher = _fetch_json,
) -> list[CdpCandidate]:
    candidates: list[CdpCandidate] = []
    for port in ports or configured_ports():
        try:
            fetch_json(f"http://{host}:{port}/json/version", timeout)
            rows = fetch_json(f"http://{host}:{port}/json/list", timeout)
            tabs = [
                {
                    "url": str(row.get("url") or ""),
                    "title": str(row.get("title") or "")[:160],
                    "type": str(row.get("type") or ""),
                }
                for row in rows
                if isinstance(row, dict)
            ]
            candidates.append(CdpCandidate(port=port, available=True, tabs=tabs))
        except Exception as exc:  # noqa: BLE001 - CDP 세션 후보 탐색 -- 도메인 추출 실패 시 빈 문자열, 후보 조회 실패는 unavailable로 기록(에러 메시지 180자로 절단)
            candidates.append(CdpCandidate(port=port, available=False, tabs=[], error=str(exc)[:180]))
    return candidates


def select_cdp_session(
    *,
    target_domains: list[str],
    avoid_domains: list[str],
    ports: list[int] | None = None,
    candidates: list[CdpCandidate] | None = None,
    host: str = DEFAULT_HOST,
) -> dict[str, Any]:
    normalized_targets = [item.lower().strip() for item in target_domains if item.strip()]
    normalized_avoid = [item.lower().strip() for item in avoid_domains if item.strip()]
    rows = candidates if candidates is not None else discover_cdp_candidates(ports=ports, host=host)
    detected = []
    selectable_target = []
    selectable_clean = []
    conflicts = []
    avoided = []

    for row in rows:
        tab_domains = [_domain(tab.get("url", "")) for tab in row.tabs]
        target_hits = [domain for domain in tab_domains if _matches(domain, normalized_targets)]
        avoid_hits = [domain for domain in tab_domains if _matches(domain, normalized_avoid)]
        item: dict[str, Any] = {
            "port": row.port,
            "available": row.available,
            "tab_count": len(row.tabs),
            "target_tab_count": len(target_hits),
            "avoid_tab_count": len(avoid_hits),
            "domains": sorted({domain for domain in tab_domains if domain}),
            "error": row.error,
        }
        detected.append(item)
        if not row.available:
            continue
        if target_hits and avoid_hits:
            conflicts.append(item)
            continue
        if avoid_hits:
            avoided.append(item)
            continue
        if target_hits:
            selectable_target.append(item)
            continue
        selectable_clean.append(item)

    selected = None
    reason = ""
    if selectable_target:
        selected = sorted(selectable_target, key=lambda item: (-item["target_tab_count"], item["port"]))[0]
        reason = "existing_target_domain_tab"
    elif selectable_clean:
        selected = sorted(selectable_clean, key=lambda item: (item["tab_count"], item["port"]))[0]
        reason = "clean_available_session"

    if selected:
        return {
            "ok": True,
            "status": "ok",
            "selected_cdp_port": selected["port"],
            "selected_reason": reason,
            "detected_tabs": detected,
            "avoided_domains": normalized_avoid,
            "cross_work_conflict": False,
        }

    return {
        "ok": False,
        "status": "blocked",
        "reason": "cdp_session_conflict_or_unavailable" if conflicts or avoided else "cdp_session_unavailable",
        "selected_cdp_port": 0,
        "selected_reason": "",
        "detected_tabs": detected,
        "avoided_domains": normalized_avoid,
        "cross_work_conflict": bool(conflicts),
        "next_step": "Open a clean CDP browser session or close tabs from other work domains, then retry.",
    }


__all__ = [
    "CdpCandidate",
    "configured_ports",
    "discover_cdp_candidates",
    "select_cdp_session",
]
