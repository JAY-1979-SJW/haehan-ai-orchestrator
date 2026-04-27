"""Playwright 기반 read-only 웹 페이지 조회 커넥터.

원칙:
- 로그인 자동화 금지 (쿠키/세션/스토리지 지속 금지)
- 외부 공개 http/https URL 에 대한 1회 read-only 접근만 허용
- localhost / 내부망 / file:// / ftp:// 등 금지된 대상은 URL 검증 단계에서 차단
- 스크린샷/다운로드/파일 저장 금지
- 도메인 allowlist(정부/공공기관) 에 속하지 않으면 차단 (운영 통제)
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 차단 사유 상수 (executor/테스트에서 공용 참조)
BLOCKED_INVALID_TARGET = "BLOCKED_INVALID_TARGET"

# 페이지 로딩/네트워크 제한
DEFAULT_GOTO_TIMEOUT_MS = 10_000
SNIPPET_MAX_CHARS = 1000

_BLOCKED_HOSTNAMES = {
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "broadcasthost",
}

# 허용 도메인(exact host). 운영 초기는 보수적으로 정부/공공기관 사이트 한정.
# 확장은 운영 정책 단계에서 별도 승인 후 추가.
ALLOWED_HOSTS = frozenset({
    "law.go.kr",
    "www.law.go.kr",
    "kosha.or.kr",
    "www.kosha.or.kr",
    "moel.go.kr",
    "www.moel.go.kr",
    "g2b.go.kr",
    "www.g2b.go.kr",
})


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_private_ip(host: str) -> bool:
    """호스트 문자열이 사설망/루프백/링크로컬 IP 면 True."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(url: str) -> tuple[bool, str]:
    """대상 URL 이 허용 기준에 부합하면 (True, "") 반환, 아니면 (False, reason).

    허용 규칙(모두 통과해야 허용):
      1) http:// 또는 https:// 스킴
      2) localhost / 루프백 / 사설망 / .local mDNS 아님
      3) ALLOWED_HOSTS (exact host) 에 포함

    차단 예시:
      - 빈 문자열, file://, ftp:// 등 타 스킴
      - 127.0.0.1 / 10.0.0.1 / ::1 등 내부 IP
      - allowlist 밖 외부 도메인 → host_not_allowed
    """
    if not isinstance(url, str) or not url.strip():
        return False, "empty_url"

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False, "malformed_url"

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False, f"scheme_not_allowed:{scheme or 'none'}"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "missing_host"

    if host in _BLOCKED_HOSTNAMES:
        return False, f"blocked_host:{host}"

    # IPv6 루프백/링크로컬 등 — hostname 은 이미 대괄호가 제거된 상태
    if _is_private_ip(host):
        return False, f"blocked_private_ip:{host}"

    # 내부망으로 흔히 쓰이는 .local mDNS 는 차단
    if host.endswith(".local"):
        return False, "blocked_mdns_local"

    # 도메인 allowlist (exact host) 검사
    if host not in ALLOWED_HOSTS:
        return False, f"host_not_allowed:{host}"

    return True, ""


def _error_payload(
    message: str,
    *,
    url: str = "",
    timed_out: bool = False,
) -> dict:
    """표준 error payload. 민감정보 없는 메시지만 포함."""
    return {
        "status": "error",
        "error": message,
        "data": {
            "url": url,
            "timed_out": timed_out,
        },
    }


def fetch_web_page(
    url: str,
    *,
    timeout_ms: int = DEFAULT_GOTO_TIMEOUT_MS,
    snippet_max_chars: int = SNIPPET_MAX_CHARS,
) -> dict:
    """공개 웹 페이지 1개를 read-only 로 조회한다.

    반환 (성공):
      {
        "status": "success",
        "data": {
          "url": <requested>, "final_url": <resolved>,
          "title": str, "snippet": str (<=1000),
          "http_status": int|None,
          "fetched_at": ISO8601(UTC),
          "timed_out": False
        }
      }

    반환 (실패):
      {"status": "error", "error": <msg>, "data": {"url": <requested>, "timed_out": bool}}
    """
    requested_url = url.strip() if isinstance(url, str) else ""

    ok, reason = validate_url(url)
    if not ok:
        logger.warning("fetch_web_page 차단 | reason=%s", reason)
        return _error_payload(
            f"{BLOCKED_INVALID_TARGET}:{reason}",
            url=requested_url,
            timed_out=False,
        )

    try:
        from playwright.sync_api import (  # type: ignore
            sync_playwright,
            TimeoutError as PwTimeoutError,
        )
    except ImportError as e:
        logger.error("playwright 미설치: %s", e)
        return _error_payload(
            "playwright_not_installed", url=requested_url, timed_out=False,
        )

    result: dict = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    try:
                        timed_out = False
                        response = None
                        try:
                            response = page.goto(
                                requested_url,
                                wait_until="domcontentloaded",
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            timed_out = True

                        if timed_out:
                            result = _error_payload(
                                "playwright_timeout",
                                url=requested_url,
                                timed_out=True,
                            )
                        else:
                            try:
                                http_status = (
                                    int(response.status) if response is not None else None
                                )
                            except Exception:  # noqa: BLE001
                                http_status = None
                            try:
                                final_url = page.url or requested_url
                            except Exception:  # noqa: BLE001
                                final_url = requested_url
                            try:
                                title = (page.title() or "").strip()
                            except Exception:  # noqa: BLE001
                                title = ""
                            snippet = ""
                            try:
                                body_text = page.locator("body").inner_text(
                                    timeout=timeout_ms
                                ) or ""
                                snippet = body_text[:snippet_max_chars]
                            except PwTimeoutError:
                                # 본문 추출 타임아웃 — 페이지는 받았으나 부분 결과.
                                logger.warning(
                                    "body innerText timeout | url=%s", requested_url,
                                )
                            except Exception as body_err:  # noqa: BLE001
                                logger.warning(
                                    "body innerText 추출 실패: %s", body_err,
                                )
                            result = {
                                "status": "success",
                                "data": {
                                    "url": requested_url,
                                    "final_url": final_url,
                                    "title": title,
                                    "snippet": snippet,
                                    "http_status": http_status,
                                    "fetched_at": _iso_utc_now(),
                                    "timed_out": False,
                                },
                            }
                    finally:
                        page.close()
                finally:
                    context.close()
            finally:
                browser.close()
    except PwTimeoutError:
        logger.warning("fetch_web_page 최상위 timeout | url=%s", requested_url)
        return _error_payload(
            "playwright_timeout", url=requested_url, timed_out=True,
        )
    except Exception as e:  # noqa: BLE001  (Playwright 는 다양한 예외 타입 발생)
        logger.warning(
            "fetch_web_page 실행 실패 | url=%s | err=%s", requested_url, e,
        )
        return _error_payload(
            f"playwright_error:{type(e).__name__}",
            url=requested_url, timed_out=False,
        )

    return result


__all__ = [
    "fetch_web_page",
    "validate_url",
    "BLOCKED_INVALID_TARGET",
    "DEFAULT_GOTO_TIMEOUT_MS",
    "SNIPPET_MAX_CHARS",
    "ALLOWED_HOSTS",
]
