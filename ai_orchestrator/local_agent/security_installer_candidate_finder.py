"""Security Installer Candidate Finder — 공식 사이트 내 설치 링크 후보를 수집한다."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# 허용 확장자
_ALLOWED_EXTENSIONS = frozenset((".exe", ".msi", ".dmg", ".pkg", ".zip"))

# 차단 확장자
_BLOCKED_EXTENSIONS = frozenset(
    (
        ".bat",
        ".cmd",
        ".ps1",
        ".js",
        ".vbs",
        ".sh",
        ".pfx",
        ".p12",
        ".key",
        ".pem",
        ".crt",
        ".cer",
        ".jks",
        ".der",
        ".p7b",
    )
)

# 차단 파일명 키워드
_BLOCKED_FILENAME_KEYWORDS = frozenset(
    (
        "password",
        "secret",
        "token",
        "cookie",
        "session",
        "credential",
        "private",
        "npki",
    )
)

# 단축 URL 패턴
_SHORTURL_PATTERNS = (
    "bit.ly",
    "tinyurl.com",
    "goo.gl",
    "t.co",
    "ow.ly",
    "short.link",
    "url.kr",
    "me2.do",
)

# NPKI 경로 패턴
_NPKI_PATH_PATTERNS = ("npki", "NPKI", "공인인증서", "인증서저장소")


def find_installer_candidates(
    page_data: dict[str, Any],
    source_host: str | None = None,
) -> dict[str, Any]:
    """
    페이지의 링크에서 설치 파일 후보를 수집하고 검증한다.

    Args:
        page_data: 현재 페이지 관찰 데이터
        source_host: 공식 출처 호스트 (없으면 page url 기준)

    Returns:
        {
            "allowed": list[dict],   # 허용 후보
            "blocked": list[dict],   # 차단 후보
            "total_found": int,
            "source_host": str,
            "server_browser_used": False,
        }
    """
    url = page_data.get("url", "")
    links = page_data.get("links", [])

    if not source_host:
        source_host = _extract_host(url)

    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for link in links:
        result = _evaluate_link(link, source_host)
        if result["allowed"]:
            allowed.append(result)
        else:
            blocked.append(result)

    return {
        "allowed": allowed,
        "blocked": blocked,
        "total_found": len(allowed) + len(blocked),
        "source_host": source_host,
        "server_browser_used": False,
    }


def validate_installer_url(url: str, source_host: str) -> dict[str, Any]:
    """단일 URL의 설치 파일 허용 여부를 검증한다."""
    return _evaluate_link(url, source_host)


def _evaluate_link(link: str, source_host: str) -> dict[str, Any]:
    lower = link.lower()
    filename = link.split("/")[-1].split("?")[0]
    filename_lower = filename.lower()

    # 단축 URL 차단
    if any(p in lower for p in _SHORTURL_PATTERNS):
        return _blocked(link, "단축 URL 차단")

    # NPKI 경로 차단
    if any(p in link for p in _NPKI_PATH_PATTERNS):
        return _blocked(link, "NPKI/인증서 경로 차단")

    # 차단 키워드 파일명 확인
    for kw in _BLOCKED_FILENAME_KEYWORDS:
        if kw in filename_lower:
            return _blocked(link, f"파일명 차단 키워드: {kw}")

    # 확장자 추출
    ext = _get_extension(filename_lower)

    if ext in _BLOCKED_EXTENSIONS:
        return _blocked(link, f"차단 확장자: {ext}")

    if ext not in _ALLOWED_EXTENSIONS and ext != "":
        return _blocked(link, f"허용되지 않은 확장자: {ext}")

    # 도메인 검증 (절대 URL인 경우)
    if link.startswith("http"):
        link_host = _extract_host(link)
        if not _is_official_domain(link_host, source_host):
            return _blocked(link, f"비공식 도메인: {link_host} (기준: {source_host})")

    # zip은 추가 승인 필요 표시
    needs_extra_approval = ext == ".zip"

    return {
        "url": link,
        "filename": filename,
        "extension": ext,
        "allowed": True,
        "block_reason": None,
        "needs_extra_approval": needs_extra_approval,
        "requires_permission": True,
    }


def _blocked(url: str, reason: str) -> dict[str, Any]:
    filename = url.split("/")[-1].split("?")[0]
    return {
        "url": url,
        "filename": filename,
        "extension": _get_extension(filename.lower()),
        "allowed": False,
        "block_reason": reason,
        "needs_extra_approval": False,
        "requires_permission": False,
    }


def _get_extension(filename: str) -> str:
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1]
    return ""


def _extract_host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001 - URL에서 호스트 추출 실패 시 빈 문자열 반환 — 이후 _is_official_domain 등에서 빈 호스트는 매칭 실패(False)로 처리되어 fail-closed
        return ""


def _is_official_domain(link_host: str, source_host: str) -> bool:
    """link_host가 source_host의 공식 도메인이나 하위 도메인인지 확인."""
    if not link_host or not source_host:
        return False
    # 동일 호스트
    if link_host == source_host:
        return True
    # 하위 도메인
    if link_host.endswith("." + source_host):
        return True
    # source_host가 하위 도메인인 경우 루트 도메인 비교
    source_root = _root_domain(source_host)
    link_root = _root_domain(link_host)
    if source_root and link_root and source_root == link_root:
        return True
    return False


def _root_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host
