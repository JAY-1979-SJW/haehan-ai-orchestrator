"""Server Egress Policy — 서버 코드의 외부 URL 직접 요청 차단."""
from __future__ import annotations

from urllib.parse import urlparse

from ai_orchestrator.server.execution_location_guard import _is_internal_host

# 명시적으로 차단하는 외부 host 패턴 (방어 강화)
_EXPLICIT_BLOCKED_HOSTS = (
    "naver.com", "g2b.go.kr", "gov.kr", "kbstar.com",
    "wooribank.com", "hometax.go.kr", "bank", "card",
    "kakao.com", "daum.net",
)

# 허용 host (allowlist) — 내부 서비스 + localhost
# 추가 host는 환경변수나 config로 확장 가능
_ALLOWLIST_HOSTS = frozenset((
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
))


def is_internal_url(url: str) -> bool:
    """URL이 내부(서버 실행 허용) URL인지 확인."""
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in _ALLOWLIST_HOSTS:
        return True
    return _is_internal_host(host)


def is_external_url(url: str) -> bool:
    """URL이 외부(서버 실행 금지) URL인지 확인."""
    if not url:
        return False
    return not is_internal_url(url)


def assert_server_egress_allowed(url: str) -> None:
    """외부 URL이면 PermissionError raise."""
    if is_external_url(url):
        host = (urlparse(url).hostname or "")
        raise PermissionError(
            f"BLOCKED_EXTERNAL_URL_FROM_SERVER: 서버에서 외부 URL 직접 접근 금지. "
            f"host={host}. local agent로 handoff 하세요."
        )


def sanitize_blocked_url_for_log(url: str) -> str:
    """로그용 URL — query/token 제거, host+path만 남김."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.hostname or ''}{parsed.path or ''}"
    except Exception:
        return "(invalid_url)"


def get_blocked_host_category(url: str) -> str:
    """차단 host의 카테고리(은행/정부/포털 등)를 반환."""
    if not url:
        return "UNKNOWN"
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return "UNKNOWN"
    if not host:
        return "UNKNOWN"
    for pat in _EXPLICIT_BLOCKED_HOSTS:
        if pat in host:
            if "go.kr" in host or "gov.kr" in host:
                return "GOVERNMENT"
            if "bank" in host or "kbstar" in host or "wooribank" in host:
                return "BANK"
            if "card" in host:
                return "CARD"
            if "naver" in host or "kakao" in host or "daum" in host:
                return "PORTAL"
    if is_external_url(url):
        return "EXTERNAL_OTHER"
    return "INTERNAL"
