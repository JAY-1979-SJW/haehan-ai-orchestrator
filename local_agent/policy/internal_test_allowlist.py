"""Stage 12M — 내부 테스트 URL controlled observe allowlist.

Stage 12L 정책 문서를 코드로 고정한다. 이 모듈은 read-only fixture/검증용이며,
호출자가 명시적으로 사용해야만 동작한다 (browser_reader 기본 동작은 무변경).

핵심 정책:
  - scheme: http only
  - host: 정확히 'localhost' 또는 '127.0.0.1' (mDNS / IPv6 / 사설망 / wildcard 모두 BLOCK)
  - port: 호출자가 지정한 정확한 단일 포트만
  - path: allowed_path_prefix 로 시작 (기본 '/__haehan_test__/readonly')
          path traversal ('..', '%2e%2e') 차단
  - query: 비어 있어야 함
  - fragment: 비어 있어야 함
  - 위험 경로 키워드 (login/admin/payment/delete 등) 추가 차단

페이지 안전성 검사는 ``analyze_internal_page_safety`` 가 담당하며, page_structure +
선택적으로 raw HTML 을 받아 password/file input/form-post/textarea/contenteditable
존재 여부를 BLOCK 사유로 반환한다.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# ── 정책 상수 ────────────────────────────────────────────────────────────────

ALLOWED_SCHEME: str = "http"
ALLOWED_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1"})
DEFAULT_ALLOWED_PATH_PREFIX: str = "/__haehan_test__/readonly"

# 위험 경로 키워드 — 경로/쿼리에 포함되면 BLOCK
RISKY_PATH_KEYWORDS: tuple[str, ...] = (
    "login", "signin", "sign-in", "auth", "oauth", "sso",
    "payment", "checkout", "order", "pay",
    "delete", "remove", "withdraw", "cancel",
    "admin", "role", "permission", "grant", "revoke",
)

# query 가 비어 있더라도, 향후 호환을 위해 위험 키 패턴(예시)
RISKY_QUERY_KEYS: tuple[str, ...] = (
    "token", "session", "password", "key", "secret", "auth", "cookie",
)


# ── URL 게이트 ───────────────────────────────────────────────────────────────

def validate_internal_test_url(
    url: str,
    *,
    allowed_port: int,
    allowed_path_prefix: str = DEFAULT_ALLOWED_PATH_PREFIX,
) -> dict[str, Any]:
    """내부 테스트 URL 정확 매칭 검사.

    ``ok == True`` 일 때만 호출자가 controlled open 으로 진행해야 한다. 이 함수는
    네트워크 호출 / 브라우저 기동을 수행하지 않으며, 순수 문자열/파싱 검사만 한다.

    반환 dict:
      - ok: bool
      - error_code: 실패 시 (예: URL_EMPTY, URL_SCHEME_BLOCKED, URL_HOST_BLOCKED,
                              URL_PORT_BLOCKED, URL_PATH_BLOCKED, URL_QUERY_BLOCKED,
                              URL_FRAGMENT_BLOCKED, URL_PATH_TRAVERSAL,
                              URL_RISKY_KEYWORD)
      - reason: 짧은 한글 메시지
      - 성공 시: scheme/host/port/path 보조 필드
    """
    if not isinstance(url, str) or not url.strip():
        return _block("URL_EMPTY", "url 누락")
    if not isinstance(allowed_port, int) or allowed_port <= 0 or allowed_port > 65535:
        return _block("URL_PORT_BLOCKED", "허용 포트 미지정 또는 잘못됨")

    raw = url.strip()

    # path traversal 방어 (raw 문자열 단위 — urlparse 가 정규화하지 않음)
    lowered = raw.lower()
    if (".." in raw) or ("%2e%2e" in lowered) or ("%2e." in lowered) or (".%2e" in lowered):
        return _block("URL_PATH_TRAVERSAL", "path traversal 패턴 감지")

    try:
        parsed = urlparse(raw)
    except ValueError:
        return _block("URL_PARSE_FAILED", "URL 파싱 실패")

    scheme = (parsed.scheme or "").lower()
    if scheme != ALLOWED_SCHEME:
        return _block(
            "URL_SCHEME_BLOCKED",
            f"허용되지 않은 스킴: {scheme or '(missing)'} (http only)",
        )

    host = (parsed.hostname or "").lower()
    if not host:
        return _block("URL_HOST_BLOCKED", "host 누락")
    if host not in ALLOWED_HOSTS:
        return _block(
            "URL_HOST_BLOCKED",
            f"허용 host 아님: {host} (localhost/127.0.0.1 only)",
        )

    port_block = _port_block(parsed, allowed_port)
    if port_block is not None:
        return port_block
    actual_port = parsed.port

    path = parsed.path or ""
    path_block = _path_block(parsed, path, allowed_path_prefix)
    if path_block is not None:
        return path_block

    return {
        "ok": True,
        "scheme": scheme,
        "host": host,
        "port": actual_port,
        "path": path,
        "url_category": "internal_test",
        "allowlist_name": "internal_test_default",
    }


def _port_block(parsed: Any, allowed_port: int) -> dict[str, Any] | None:
    """포트 검사. 통과하면 None."""
    # urlparse.port 는 허용되지 않은 포트(예: 0)에서 ValueError. try/except 로 안전화.
    try:
        actual_port = parsed.port
    except ValueError:
        return _block("URL_PORT_BLOCKED", "포트 파싱 실패")
    if actual_port is None:
        return _block("URL_PORT_BLOCKED", "명시 포트 누락")
    if actual_port != allowed_port:
        return _block(
            "URL_PORT_BLOCKED",
            f"허용 포트 아님: {actual_port} != {allowed_port}",
        )
    return None


def _path_block(parsed: Any, path: str, allowed_path_prefix: str) -> dict[str, Any] | None:
    """path prefix / query / fragment / 위험 키워드 검사. 통과하면 None."""
    if not path.startswith(allowed_path_prefix):
        return _block(
            "URL_PATH_BLOCKED",
            f"허용 path prefix 아님: {path[:60]}",
        )

    if parsed.query:
        return _block("URL_QUERY_BLOCKED", "query 가 비어있어야 함")
    if parsed.fragment:
        return _block("URL_FRAGMENT_BLOCKED", "fragment 가 비어있어야 함")

    # 위험 경로 키워드 (path 만 검사 — query 는 위에서 이미 빈 값으로 강제)
    path_lower = path.lower()
    for kw in RISKY_PATH_KEYWORDS:
        if kw in path_lower:
            return _block(
                "URL_RISKY_KEYWORD",
                f"위험 경로 키워드 포함: {kw}",
            )
    return None


# ── 페이지 안전성 ────────────────────────────────────────────────────────────

def analyze_internal_page_safety(
    page_structure: dict[str, Any],
    *,
    final_url: str = "",
    allowed_port: int | None = None,
    allowed_path_prefix: str = DEFAULT_ALLOWED_PATH_PREFIX,
    raw_html_for_contenteditable_check: str | None = None,
) -> dict[str, Any]:
    """관찰 결과(page_structure + final_url) 가 controlled observe 안전 기준에 부합하는지 검사.

    BLOCK 사유:
      - PASSWORD_INPUT_PRESENT
      - FILE_INPUT_PRESENT
      - FORM_POST_PRESENT
      - TEXTAREA_PRESENT
      - CONTENTEDITABLE_PRESENT (raw_html 제공 시에만)
      - FINAL_URL_OUTSIDE_ALLOWLIST (allowed_port 제공 시 재검증)
    """
    if not isinstance(page_structure, dict):
        return {"safe": False, "blocked_reason": "PAGE_STRUCTURE_INVALID"}

    blocked = _input_form_block_reason(page_structure)
    if blocked is not None:
        return {"safe": False, "blocked_reason": blocked}

    textareas = page_structure.get("textareas") or []
    if textareas:
        return {"safe": False, "blocked_reason": "TEXTAREA_PRESENT"}

    if isinstance(raw_html_for_contenteditable_check, str):
        if "contenteditable" in raw_html_for_contenteditable_check.lower():
            return {"safe": False, "blocked_reason": "CONTENTEDITABLE_PRESENT"}

    if final_url and allowed_port is not None:
        # final_url 이 allowlist 안에 있는지 재검증 (navigation 후 escape 방지)
        check = validate_internal_test_url(
            final_url,
            allowed_port=allowed_port,
            allowed_path_prefix=allowed_path_prefix,
        )
        if not check.get("ok"):
            return {
                "safe": False,
                "blocked_reason": "FINAL_URL_OUTSIDE_ALLOWLIST",
            }

    return {"safe": True, "blocked_reason": None}


def _input_form_block_reason(page_structure: dict[str, Any]) -> str | None:
    """input/form 기반 BLOCK 사유(없으면 None). 검사 순서 고정."""
    inputs = page_structure.get("inputs") or []
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        itype = (inp.get("type") or "").lower()
        if itype == "password":
            return "PASSWORD_INPUT_PRESENT"
        if itype == "file":
            return "FILE_INPUT_PRESENT"

    forms = page_structure.get("forms") or []
    for f in forms:
        if not isinstance(f, dict):
            continue
        method = (f.get("method") or "get").lower()
        if method == "post":
            return "FORM_POST_PRESENT"
        if f.get("has_password"):
            return "PASSWORD_INPUT_PRESENT"
    return None


# ── 내부 ────────────────────────────────────────────────────────────────────

def _block(error_code: str, reason: str) -> dict[str, Any]:
    return {"ok": False, "error_code": error_code, "reason": reason[:200]}


__all__ = [
    "ALLOWED_SCHEME",
    "ALLOWED_HOSTS",
    "DEFAULT_ALLOWED_PATH_PREFIX",
    "RISKY_PATH_KEYWORDS",
    "RISKY_QUERY_KEYS",
    "validate_internal_test_url",
    "analyze_internal_page_safety",
]
