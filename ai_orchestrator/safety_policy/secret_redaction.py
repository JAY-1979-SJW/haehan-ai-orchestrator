"""Secret Redaction — 단일 기준선 비밀 필드 제거/검증 헬퍼.

이 모듈이 프로젝트 내 secret redaction의 단일 source of truth다.
기존 분산 구현(task_queue_service._FORBIDDEN_FIELDS, domain/models.DOMAIN_FORBIDDEN_FIELDS)은
이 모듈의 FORBIDDEN_SECRET_FIELDS를 참조하거나 호환 상태로 유지한다.

금지:
- 실제 secret 값 출력 금지
- 테스트 시 real credential 사용 금지
- API 응답 구조 변경 금지
"""
from __future__ import annotations

from typing import Any

# 단일 금지 키 기준선
FORBIDDEN_SECRET_FIELDS: frozenset[str] = frozenset({
    # 인증 자격증명
    "password", "passwd", "pwd",
    "otp",
    "token", "access_token", "refresh_token", "auth_token", "device_token",
    "api_key", "client_secret",
    "session", "cookie", "cookies",
    "credential", "credentials",
    "secret",
    "private_key",
    "authorization",
    # 인증서
    "cert_password", "certificate_password", "certificate_file_path",
    "npki", "npki_data",
    # 승인 토큰
    "approval_token", "final_approval_token", "token_hash",
    # 브라우저 저장소
    "localstorage", "sessionstorage",
    # 파일/바이너리 (민감 콘텐츠)
    "raw_screenshot", "base64",
    "file_content", "file_bytes", "file_data",
    "attachment_content", "attachment_bytes",
    # 헤더
    "auth_header",
    # 기기
    "typed_text",
})

_REDACTED_PLACEHOLDER = "[REDACTED]"


def list_forbidden_secret_fields() -> list[str]:
    """금지 필드 이름 목록을 정렬하여 반환한다."""
    return sorted(FORBIDDEN_SECRET_FIELDS)


def contains_forbidden_secret_key(data: dict[str, Any]) -> bool:
    """dict의 최상위 키 또는 payload 키에 금지 필드가 있으면 True."""
    for k in data:
        if k.lower() in FORBIDDEN_SECRET_FIELDS:
            return True
    payload = data.get("payload", {})
    if isinstance(payload, dict):
        for k in payload:
            if k.lower() in FORBIDDEN_SECRET_FIELDS:
                return True
    return False


def redact_sensitive_fields(
    data: dict[str, Any],
    placeholder: str = _REDACTED_PLACEHOLDER,
) -> dict[str, Any]:
    """금지 필드를 재귀적으로 placeholder로 치환한 새 dict를 반환한다.

    원본 dict는 변경하지 않는다.
    """
    result = {}
    for k, v in data.items():
        if k.lower() in FORBIDDEN_SECRET_FIELDS:
            result[k] = placeholder
        elif isinstance(v, dict):
            result[k] = redact_sensitive_fields(v, placeholder)
        else:
            result[k] = v
    return result


def strip_sensitive_fields(data: dict[str, Any]) -> dict[str, Any]:
    """금지 필드를 재귀적으로 제거한 새 dict를 반환한다.

    원본 dict는 변경하지 않는다.
    """
    result = {}
    for k, v in data.items():
        if k.lower() in FORBIDDEN_SECRET_FIELDS:
            continue
        if isinstance(v, dict):
            result[k] = strip_sensitive_fields(v)
        else:
            result[k] = v
    return result


def assert_no_sensitive_fields(data: dict[str, Any]) -> list[str]:
    """금지 필드가 있으면 위반 key 목록을 반환한다. 없으면 빈 리스트."""
    violations: list[str] = []
    for k in data:
        if k.lower() in FORBIDDEN_SECRET_FIELDS:
            violations.append(k)
    payload = data.get("payload", {})
    if isinstance(payload, dict):
        for k in payload:
            if k.lower() in FORBIDDEN_SECRET_FIELDS:
                violations.append(f"payload.{k}")
    return violations
