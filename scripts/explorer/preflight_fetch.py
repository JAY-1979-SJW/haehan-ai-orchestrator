"""L3 Connectors — 사전 조사용 단순 GET(robots.txt·sitemap.xml). 브라우저를 쓰지 않는다.

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md (M10)

- 호스트 고정: 같은 호스트 안의 이동만 따라간다(최대 3번). 다른 호스트로 넘기면 중단한다.
- 내부망·로컬 주소로 풀리는 호스트는 거부한다(시험용 `allow_local=True` 만 예외).
- 응답은 크기 상한까지만 읽고, 쿠키·인증 헤더는 보내지 않는다.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

MAX_BYTES = 262_144
TIMEOUT_S = 8.0
MAX_REDIRECTS = 3
_UA = "HaehanSiteOnboarding/1.0 (read-only preflight)"


def _is_local(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # 풀리지 않는 호스트는 연결 단계에서 실패로 처리된다
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return True
    return False


def _get_once(url: str, timeout: float) -> tuple[int, str, bytes]:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname or "", parsed.port, timeout=timeout)
    try:
        conn.request(
            "GET",
            (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else ""),
            headers={"User-Agent": _UA, "Accept": "text/plain,application/xml,*/*"},
        )
        resp = conn.getresponse()
        return resp.status, resp.getheader("Location") or "", resp.read(MAX_BYTES)
    finally:
        conn.close()


def fetch_text(url: str, *, allow_local: bool = False, timeout: float = TIMEOUT_S) -> dict[str, Any]:
    """주소 하나를 읽어 `{status, text, error}` 로 돌려준다. 실패는 예외 대신 `error` 로 알린다."""
    origin = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme not in ("http", "https") or not origin:
        return {"status": 0, "text": "", "error": "invalid_url"}
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        host = (urlparse(current).hostname or "").lower()
        if host != origin:
            return {"status": 0, "text": "", "error": "redirected_to_other_host"}
        if not allow_local and _is_local(host):
            return {"status": 0, "text": "", "error": "local_address_refused"}
        try:
            status, location, body = _get_once(current, timeout)
        except (OSError, http.client.HTTPException) as exc:
            return {"status": 0, "text": "", "error": type(exc).__name__}
        if status in (301, 302, 303, 307, 308) and location:
            current = urljoin(current, location)
            continue
        return {"status": status, "text": body.decode("utf-8", errors="replace"), "error": ""}
    return {"status": 0, "text": "", "error": "too_many_redirects"}
