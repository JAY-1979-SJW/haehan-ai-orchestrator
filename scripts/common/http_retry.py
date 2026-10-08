"""죽은 로컬 프록시 우회 HTTP 열기 — 도구 무관 공용 함수(표준 라이브러리만 사용).

환경변수 HTTP(S)_PROXY 가 127.0.0.1:9·localhost:9 같은 죽은 로컬 프록시를 가리켜 연결이 거부되면,
프록시 없이 한 번 더 연다. scripts/common/youtube_http_client.py 와
scripts/google/youtube/search_common.py 가 똑같이 복사해 쓰던 본문을 한 곳으로 모았다.

사용 예:
    from scripts.common.http_retry import urlopen_with_dead_proxy_fallback
    with urlopen_with_dead_proxy_fallback(request, timeout=20) as response: ...
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request


def urlopen_with_dead_proxy_fallback(request: urllib.request.Request, *, timeout: int):
    """URL 을 연다. 죽은 로컬 프록시로 연결이 거부되면 프록시 없이 다시 연다."""
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        if not should_retry_without_proxy(exc):
            raise
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)


def should_retry_without_proxy(exc: urllib.error.URLError) -> bool:
    """프록시 환경변수가 죽은 로컬 프록시(…:9)를 가리키고 오류가 '연결 거부'이면 True."""
    reason = str(getattr(exc, "reason", exc))
    proxy_values = [
        os.environ.get("HTTPS_PROXY", ""),
        os.environ.get("HTTP_PROXY", ""),
        os.environ.get("https_proxy", ""),
        os.environ.get("http_proxy", ""),
    ]
    dead_local_proxy = any("127.0.0.1:9" in value or "localhost:9" in value for value in proxy_values)
    return dead_local_proxy and ("10061" in reason or "Connection refused" in reason or "연결을 거부" in reason)
