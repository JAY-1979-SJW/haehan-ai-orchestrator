"""
Local Agent User-Present WebSocket Message Contract

routing dry-run 결과가 LOCAL_SYSTEM_BROWSER_USER_PRESENT인 경우
서버→로컬 Agent 간 message contract를 정의한다.

safe_to_execute: 항상 False.
password/otp/certificate_password/token/cookie/session 전송 금지.
raw target_url 전송 금지 (redacted/hash만 허용).
실제 WebSocket 운영 송신 없음.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

# ── message_type 상수 ─────────────────────────────────────────────────────────

MSG_USER_PRESENT_TASK = "USER_PRESENT_TASK"
MSG_USER_PRESENT_STATUS = "USER_PRESENT_STATUS"

# ── status 허용값 ─────────────────────────────────────────────────────────────

STATUS_WAITING_FOR_USER = "WAITING_FOR_USER"
STATUS_USER_CONFIRMED = "USER_CONFIRMED"
STATUS_CANCELLED = "CANCELLED"
STATUS_BLOCKED = "BLOCKED"
STATUS_FAILED = "FAILED"

_VALID_STATUS_VALUES: frozenset[str] = frozenset(
    {
        STATUS_WAITING_FOR_USER,
        STATUS_USER_CONFIRMED,
        STATUS_CANCELLED,
        STATUS_BLOCKED,
        STATUS_FAILED,
    }
)

# ── 전송 금지 필드 ────────────────────────────────────────────────────────────

_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "certificate_password",
        "financial_certificate_password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "device_token",
        "cookie",
        "session",
        "localStorage",
        "sessionStorage",
        "secret",
        "raw_audit",
        "audit_raw",
        "internal_policy",
        "full_policy",
        "cross_tenant_data",
        "other_user_tasks",
        "other_tenant_data",
        "raw_validation_errors",
        "system_trace",
        # raw URL은 금지 — redacted/hash만 허용
        "target_url",
    }
)

# ── auth_method 한글 라벨 ─────────────────────────────────────────────────────

_AUTH_METHOD_LABELS: dict[str, str] = {
    "certificate": "공동인증서/공인인증서",
    "financial_certificate": "금융인증서",
    "otp": "OTP (일회용 비밀번호)",
    "security_card": "보안카드",
    "simple_auth": "간편인증 (PASS/카카오/네이버)",
    "password": "비밀번호",
}

# ── 사이트 분류별 기본 안내 문구 ──────────────────────────────────────────────

_SITE_CATEGORY_MESSAGES: dict[str, str] = {
    "bank": "은행 사이트 접속에 사용자 직접 인증이 필요합니다.",
    "card": "카드사 사이트 접속에 사용자 직접 인증이 필요합니다.",
    "hometax": "홈택스 접속에 공동인증서/금융인증서 인증이 필요합니다.",
    "tax": "세무 사이트 접속에 사용자 직접 인증이 필요합니다.",
    "gov24": "정부24 접속에 사용자 직접 인증이 필요합니다.",
    "government": "정부 사이트 접속에 사용자 직접 인증이 필요합니다.",
    "four_insurance": "4대보험 사이트 접속에 공동인증서 인증이 필요합니다.",
    "insurance": "보험 사이트 접속에 사용자 직접 인증이 필요합니다.",
    "certificate_portal": "인증서 발급 포털 접속에 사용자 직접 인증이 필요합니다.",
    "certificate": "인증서 관련 사이트 접속에 사용자 직접 인증이 필요합니다.",
}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _hash_url(url: str) -> str:
    if not url:
        return ""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _redact_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/***"
    except Exception:  # noqa: BLE001 - URL 마스킹 실패 시 '***' 로 완전 마스킹 반환 — fail-safe, 원본 URL 노출 없음
        return "***"


def sanitize_user_present_ws_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    전송 전 민감정보를 제거한다.
    raw target_url은 제거하고 redacted/hash로 대체한다.
    """
    clean: dict[str, Any] = {}
    raw_url = payload.get("target_url", "")

    for k, v in payload.items():
        if k in _FORBIDDEN_KEYS:
            continue
        clean[k] = v

    # target_url은 redacted/hash만 포함
    if raw_url and "target_url_redacted" not in clean:
        clean["target_url_redacted"] = _redact_url(raw_url)
    if raw_url and "target_url_hash" not in clean:
        clean["target_url_hash"] = _hash_url(raw_url)

    return clean


def build_user_present_ws_task_message(payload: dict[str, Any]) -> dict[str, Any]:
    """
    서버 → 로컬 Agent USER_PRESENT_TASK message를 구성한다.
    민감정보 제거 후 전송 가능한 형태로 반환.
    """
    clean = sanitize_user_present_ws_payload(payload)

    site_category = clean.get("site_category", "")
    default_msg = _SITE_CATEGORY_MESSAGES.get(
        site_category,
        "사용자 직접 인증이 필요합니다. 브라우저에서 직접 인증을 완료해 주세요.",
    )

    auth_methods: list[str] = clean.get("auth_methods", [])
    if isinstance(auth_methods, str):
        auth_methods = [auth_methods]
    auth_label_parts = [_AUTH_METHOD_LABELS.get(m, m) for m in auth_methods]
    auth_method_label = clean.get("auth_method_label") or (
        ", ".join(auth_label_parts) if auth_label_parts else "사용자 직접 인증"
    )

    message: dict[str, Any] = {
        "message_type": MSG_USER_PRESENT_TASK,
        "workflow_run_id": clean.get("workflow_run_id", ""),
        "workflow_id": clean.get("workflow_id", ""),
        "tenant_id": clean.get("tenant_id", ""),
        "user_id": clean.get("user_id", ""),
        "site_id": clean.get("site_id", ""),
        "site_category": site_category,
        "target_domain": clean.get("target_domain", ""),
        "target_url_redacted": clean.get("target_url_redacted", ""),
        "target_url_hash": clean.get("target_url_hash", ""),
        "auth_method_label": auth_method_label,
        "user_message_ko": clean.get("user_message_ko") or default_msg,
        "required_user_actions": clean.get(
            "required_user_actions",
            [
                "브라우저에서 직접 로그인/인증을 완료하세요.",
                "완료 후 UI에서 '인증 완료' 버튼을 클릭하세요.",
            ],
        ),
        "blocked_ai_actions": clean.get(
            "blocked_ai_actions",
            [
                "비밀번호 자동 입력 금지",
                "OTP 자동 입력 금지",
                "인증서 비밀번호 자동 입력 금지",
                "자동 클릭/폼 제출 금지",
            ],
        ),
        "safe_to_execute": False,
        "created_at": clean.get("created_at") or _now_iso(),
    }
    return message


def build_user_present_ws_status_event(payload: dict[str, Any]) -> dict[str, Any]:
    """
    로컬 Agent → 서버 USER_PRESENT_STATUS event를 구성한다.
    safe_to_execute는 항상 False.
    """
    status = payload.get("status", STATUS_WAITING_FOR_USER)
    event: dict[str, Any] = {
        "message_type": MSG_USER_PRESENT_STATUS,
        "workflow_run_id": payload.get("workflow_run_id", ""),
        "tenant_id": payload.get("tenant_id", ""),
        "user_id": payload.get("user_id", ""),
        "site_id": payload.get("site_id", ""),
        "status": status,
        "status_reason": payload.get("status_reason", ""),
        "safe_to_execute": False,
        "created_at": payload.get("created_at") or _now_iso(),
    }
    return event


def validate_user_present_ws_task_message(message: dict[str, Any]) -> list[str]:
    """USER_PRESENT_TASK message 필수 필드 및 정책 검증."""
    errors: list[str] = []

    required = [
        "message_type",
        "workflow_run_id",
        "tenant_id",
        "user_id",
        "site_id",
        "site_category",
        "target_domain",
        "target_url_redacted",
        "target_url_hash",
        "auth_method_label",
        "user_message_ko",
        "required_user_actions",
        "blocked_ai_actions",
        "safe_to_execute",
        "created_at",
    ]
    for field in required:
        if field not in message:
            errors.append(f"필수 필드 누락: {field}")

    if message.get("message_type") != MSG_USER_PRESENT_TASK:
        errors.append(f"message_type 오류: {message.get('message_type')}")

    if message.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    if not message.get("workflow_run_id"):
        errors.append("workflow_run_id는 비어있을 수 없다")

    if not message.get("tenant_id"):
        errors.append("tenant_id는 비어있을 수 없다")

    if not message.get("user_id"):
        errors.append("user_id는 비어있을 수 없다")

    # 민감 필드 포함 여부 확인
    for forbidden in _FORBIDDEN_KEYS:
        if forbidden in message:
            errors.append(f"금지 필드 포함: {forbidden}")

    return errors


def validate_user_present_ws_status_event(event: dict[str, Any]) -> list[str]:
    """USER_PRESENT_STATUS event 필수 필드 및 정책 검증."""
    errors: list[str] = []

    required = [
        "message_type",
        "workflow_run_id",
        "tenant_id",
        "user_id",
        "site_id",
        "status",
        "status_reason",
        "safe_to_execute",
        "created_at",
    ]
    for field in required:
        if field not in event:
            errors.append(f"필수 필드 누락: {field}")

    if event.get("message_type") != MSG_USER_PRESENT_STATUS:
        errors.append(f"message_type 오류: {event.get('message_type')}")

    if event.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    if event.get("status") not in _VALID_STATUS_VALUES:
        errors.append(f"유효하지 않은 status: {event.get('status')}")

    for forbidden in _FORBIDDEN_KEYS:
        if forbidden in event:
            errors.append(f"금지 필드 포함: {forbidden}")

    return errors
