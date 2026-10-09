"""공개 페이지 fallback reader 골격.

목적:
- 검색 API 결과의 link 를 후속 확인하기 위한 **최소** 메타 추출.
- 로그인 없이 열람 가능한 페이지의 <title>/og:title/meta description/canonical 만 본다.
- 본문 / 댓글 / 이미지 / 첨부 / 네이버 지식iN/쇼핑 상세 데이터 등은 수집하지 않는다.

원칙:
- HTTP transport 는 주입 (테스트 / 운영 모두 가능).
- 로그인 쿠키 / Authorization 헤더 사용 금지.
- robots.txt 우회 / fingerprint 조작 금지.
- 인증 필요 / 차단 / 비-HTML 응답이면 즉시 중단 (blocked / unsupported / error).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# 로그인이 필요한 네이버 영역. 이쪽 호스트는 자동 차단한다 (정책 우회 방지).
_LOGIN_REQUIRED_HOST_HINTS = (
    "nid.naver.com",
    "mail.naver.com",
    "calendar.naver.com",
    "cafe.naver.com",  # 비공개 게시판 가능성 — 보수적으로 차단
    "band.us",
    "checkout.naver.com",
    "order.pay.naver.com",
)


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_RE = re.compile(
    r"""<meta\s+([^>]*?)/?>""",
    re.IGNORECASE,
)
_ATTR_RE = re.compile(
    r"""(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))""",
    re.IGNORECASE,
)
_LINK_RE = re.compile(
    r"""<link\s+([^>]*?)/?>""",
    re.IGNORECASE,
)


@dataclass
class PublicPageSummary:
    status: str  # "ok" | "blocked" | "unsupported" | "error"
    url: str
    title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    error_code: str | None = None
    request_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "url": self.url,
            "title": self.title,
            "meta_description": self.meta_description,
            "canonical_url": self.canonical_url,
            "error_code": self.error_code,
            "request_summary": self.request_summary,
        }


def _parse_attrs(attrs_blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attrs_blob):
        key = m.group(1).lower()
        val = m.group(2) or m.group(3) or m.group(4) or ""
        out[key] = val
    return out


def _is_login_required_host(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("로그인 필요 호스트 판정(URL 파싱) 실패(무시): %s", type(exc).__name__)
        return False
    host = host.lower()
    return any(hint in host for hint in _LOGIN_REQUIRED_HOST_HINTS)


def _extract_title(html_text: str) -> str | None:
    m = _TITLE_RE.search(html_text)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        return title or None
    # og:title fallback 은 meta 파서에서 처리
    return None


def _extract_meta_and_canonical(html_text: str) -> tuple[str | None, str | None, str | None]:
    description: str | None = None
    og_title: str | None = None
    canonical: str | None = None

    for m in _META_RE.finditer(html_text):
        attrs = _parse_attrs(m.group(1))
        name = (attrs.get("name") or "").lower()
        prop = (attrs.get("property") or "").lower()
        content = attrs.get("content")
        if not content:
            continue
        if description is None and (name == "description" or prop == "og:description"):
            description = re.sub(r"\s+", " ", content).strip() or None
        if og_title is None and prop == "og:title":
            og_title = re.sub(r"\s+", " ", content).strip() or None

    for m in _LINK_RE.finditer(html_text):
        attrs = _parse_attrs(m.group(1))
        if (attrs.get("rel") or "").lower() == "canonical":
            href = attrs.get("href")
            if href:
                canonical = href.strip() or None
            break

    return description, canonical, og_title


def _content_type_of(headers: Any) -> str:
    """응답 헤더 dict 에서 content-type(소문자)을 찾는다. 없으면 빈 문자열."""
    if isinstance(headers, dict):
        for k, v in headers.items():
            if k.lower() == "content-type":
                return str(v or "").lower()
    return ""


def fetch_public_page_summary(
    url: str,
    *,
    transport: Callable[..., Any] | None = None,
    max_bytes: int = 256 * 1024,
) -> PublicPageSummary:
    """공개 페이지 메타 요약. 로그인/세션/대량 본문 수집을 하지 않는다.

    transport 시그니처:
        ``transport(method, url, headers) -> (status:int, headers:dict, body:str)``

    transport 가 None 이면 외부 호출을 발생시키지 않고 'unsupported' 로 종료.
    """
    summary = {"method": "GET", "url_host": (urlparse(url).hostname or "").lower()}

    if not url or not url.lower().startswith(("http://", "https://")):
        return PublicPageSummary(
            status="error",
            url=url,
            error_code="INVALID_URL",
            request_summary=summary,
        )

    if _is_login_required_host(url):
        logger.info("[NAVER-PUBLIC-READER-BLOCKED] host=%s", summary["url_host"])
        return PublicPageSummary(
            status="blocked",
            url=url,
            error_code="LOGIN_REQUIRED_HOST",
            request_summary=summary,
        )

    if transport is None:
        # 외부 의존성을 강제 주입식으로 둔다. wiring 전이면 unsupported.
        return PublicPageSummary(
            status="unsupported",
            url=url,
            error_code="TRANSPORT_NOT_WIRED",
            request_summary=summary,
        )

    try:
        http_status, headers, body = transport(
            method="GET",
            url=url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "haehan-ai-orchestrator/public-reader (read-only)",
            },
        )
    except Exception as e:
        logger.exception("[NAVER-PUBLIC-READER-ERR] type=%s", type(e).__name__)
        return PublicPageSummary(
            status="error",
            url=url,
            error_code="TRANSPORT_EXCEPTION",
            request_summary=summary,
        )

    status_int = int(http_status)
    if status_int in (401, 403):
        return PublicPageSummary(
            status="blocked",
            url=url,
            error_code=f"HTTP_{status_int}",
            request_summary=summary,
        )
    if not (200 <= status_int < 300):
        return PublicPageSummary(
            status="error",
            url=url,
            error_code=f"HTTP_{status_int}",
            request_summary=summary,
        )

    content_type = _content_type_of(headers)
    if content_type and "html" not in content_type:
        return PublicPageSummary(
            status="unsupported",
            url=url,
            error_code="NON_HTML_CONTENT",
            request_summary=summary,
        )

    text = (
        body
        if isinstance(body, str)
        else (body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else "")
    )
    if len(text) > max_bytes:
        text = text[:max_bytes]

    title = _extract_title(text)
    description, canonical, og_title = _extract_meta_and_canonical(text)
    return PublicPageSummary(
        status="ok",
        url=url,
        title=title or og_title,
        meta_description=description,
        canonical_url=canonical,
        request_summary=summary,
    )


__all__ = [
    "PublicPageSummary",
    "fetch_public_page_summary",
]
