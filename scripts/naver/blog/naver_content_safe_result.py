"""
네이버 콘텐츠 workflow safe result 빌더

모든 결과에서 민감값 제거. safe 필드 강제.
"""

from __future__ import annotations

from typing import Any

_REMOVE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "cookie",
        "cookies",
        "session",
        "token",
        "access_token",
        "refresh_token",
        "certificate_password",
        "cert_password",
        "npki",
        "npki_data",
        "private_key",
        "auth_header",
        "Authorization",
        "localStorage",
        "sessionStorage",
        "storage_state",
        "naver_id",
        "naver_password",
    }
)

_FIXED_SAFE_FIELDS: dict[str, Any] = {
    "sensitive_data_collected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "storage_state_exported": False,
    "server_browser_used": False,
}


def build_cafe_read_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    url: str,
    title: str = "",
    body_text: str = "",
    author: str = "",
    created_at: str = "",
    summary: str = "",
    keywords: list[str] | None = None,
    comment_candidates: list[str] | None = None,
    blog_material_candidates: list[str] | None = None,
    ok: bool = True,
    message_ko: str = "",
) -> dict[str, Any]:
    """카페 읽기 결과. 민감값 없음."""
    result = {
        "task_id": task_id,
        "url": url,
        "title": title,
        "body_text_sample": body_text[:500] if body_text else "",
        "author": author,
        "created_at": created_at,
        "summary": summary,
        "keywords": keywords or [],
        "comment_candidates": comment_candidates or [],
        "blog_material_candidates": blog_material_candidates or [],
        "ok": ok,
        "message_ko": message_ko or ("카페 글 읽기 완료." if ok else "카페 글 읽기 실패."),
    }
    result.update(_FIXED_SAFE_FIELDS)
    return result


def build_blog_draft_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    title_candidates: list[str] | None = None,
    body_draft: str = "",
    tag_candidates: list[str] | None = None,
    source_urls: list[str] | None = None,
    ok: bool = True,
    message_ko: str = "",
) -> dict[str, Any]:
    """블로그 초안 결과. 민감값 없음."""
    result = {
        "task_id": task_id,
        "title_candidates": title_candidates or [],
        "body_draft": body_draft,
        "tag_candidates": tag_candidates or [],
        "source_urls": source_urls or [],
        "ok": ok,
        "message_ko": message_ko or ("블로그 초안 생성 완료." if ok else "블로그 초안 생성 실패."),
    }
    result.update(_FIXED_SAFE_FIELDS)
    return result


def build_publish_result(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    task_id: str,
    action: str,
    domain: str,
    ok: bool,
    permission_id: str = "",
    published_url: str = "",
    message_ko: str = "",
    status: str = "",
) -> dict[str, Any]:
    """발행/글쓰기/댓글 실행 결과. 민감값 없음."""
    result = {
        "task_id": task_id,
        "action": action,
        "domain": domain,
        "ok": ok,
        "permission_id": permission_id,
        "published_url": published_url,
        "message_ko": message_ko or ("실행 완료." if ok else "실행 실패."),
        "status": status,
    }
    result.update(_FIXED_SAFE_FIELDS)
    return result


def sanitize_naver_result(result: dict[str, Any]) -> dict[str, Any]:
    """네이버 workflow 결과에서 민감값 제거 후 safe 필드 강제."""
    safe = {k: v for k, v in result.items() if k not in _REMOVE_FIELDS}
    safe.update(_FIXED_SAFE_FIELDS)
    return safe


def validate_naver_result(result: dict[str, Any]) -> list[str]:
    """safe 필드 위반 목록 반환. 빈 리스트면 안전."""
    violations = []
    for field in _REMOVE_FIELDS:
        if field in result and result[field] not in (None, False, ""):
            violations.append(f"민감 필드 노출: {field}")
    for field, expected in _FIXED_SAFE_FIELDS.items():
        if result.get(field) != expected:
            violations.append(f"safe 필드 위반: {field}={result.get(field)!r}")
    return violations
