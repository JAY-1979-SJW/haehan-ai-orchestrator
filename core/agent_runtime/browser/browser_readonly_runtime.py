"""
로컬 Agent read-only 브라우저 런타임 모듈

사용자 PC에서 실제 브라우저를 read-only로 열어 페이지 상태만 확인한다.
click/type/submit/download/쿠키추출은 절대 수행하지 않는다.
사용자 직접 인증이 필요한 화면 감지 시 USER_PRESENT_REQUIRED로 반환한다.

기존 core/agent_runtime/browser/browser_reader.py의 open_url_readonly()를 조율하는
정책 계층 역할을 한다.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── runtime_decision 값 ──────────────────────────────────────────────────────

DECISION_READONLY_ALLOWED = "READONLY_ALLOWED"
DECISION_REQUIRE_USER_PRESENT = "REQUIRE_USER_PRESENT"
DECISION_REQUIRE_API = "REQUIRE_API_CONNECTOR"
DECISION_BLOCK = "BLOCK"
DECISION_RUNTIME_NOT_AVAILABLE = "RUNTIME_NOT_AVAILABLE"
DECISION_FAILED = "FAILED"

# ── 상태 enum ────────────────────────────────────────────────────────────────

STATE_READY = "READY"
STATE_OPENING_BROWSER = "OPENING_BROWSER"
STATE_PAGE_LOADED = "PAGE_LOADED"
STATE_USER_PRESENT_REQUIRED = "USER_PRESENT_REQUIRED"
STATE_READONLY_RESULT_READY = "READONLY_RESULT_READY"
STATE_BLOCKED = "BLOCKED"
STATE_FAILED = "FAILED"
STATE_CANCELLED = "CANCELLED"
STATE_RUNTIME_NOT_AVAILABLE = "RUNTIME_NOT_AVAILABLE"

# ── 허용 operation_type ──────────────────────────────────────────────────────

_ALLOWED_OPERATIONS: frozenset[str] = frozenset(
    {
        "read",
        "navigate",
        "open_url",
        "readonly_search",
        "readonly_scrape",
        "readonly_status_check",
    }
)

# ── 차단 operation_type ──────────────────────────────────────────────────────

_BLOCKED_OPERATIONS: frozenset[str] = frozenset(
    {
        "click",
        "type",
        "fill",
        "submit",
        "download",
        "upload",
        "write",
        "delete",
        "update",
        "insert",
        "sign",
        "login_auto",
    }
)

# ── API 처리 사이트 카테고리 ─────────────────────────────────────────────────

_API_CATEGORIES: frozenset[str] = frozenset(
    {
        "cloud_service",
        "google",
        "google_workspace",
    }
)

# ── text_snippet 민감 키워드 (redaction 대상) ─────────────────────────────────

_SNIPPET_SENSITIVE_PATTERNS = re.compile(
    r"(password|token|cookie|session|otp|비밀번호|인증번호|보안카드|비번)",
    re.IGNORECASE,
)

# ── 인증 방법 감지 키워드 ────────────────────────────────────────────────────

_AUTH_METHOD_PATTERNS: list[tuple[str, str]] = [
    (r"공동인증서|공인인증서", "certificate"),
    (r"금융인증서", "financial_certificate"),
    (r"인증서\s*(선택|비밀번호|입력)|전자서명", "certificate"),
    (r"\bOTP\b|otp 번호|일회용", "otp"),
    (r"보안카드", "security_card"),
    (r"간편\s*인증|PASS\s*인증|카카오\s*인증|네이버\s*인증", "simple_auth"),
    (r"비밀번호\s*(입력|확인)", "password"),
]

# ── 보안 요구사항 감지 키워드 ────────────────────────────────────────────────

_SECURITY_REQ_PATTERNS: list[tuple[str, str, bool]] = [
    # (pattern, tag, is_blocker)
    (r"CAPTCHA|캡차|보안\s*문자", "captcha", True),
    (r"보안\s*프로그램|키보드\s*보안|안전\s*키패드|안전한\s*브라우저", "security_plugin", False),
    (r"원격\s*접속|원격\s*제어|원격\s*지원|원격접속\s*차단", "remote_access_warning", False),
    (r"(설치\s*(필요|후|하세요)|프로그램\s*설치)", "install_required", False),
]

# ── 사용자 직접 인증 필요 auth_method ────────────────────────────────────────

_USER_PRESENT_AUTH_METHODS: frozenset[str] = frozenset(
    {
        "certificate",
        "financial_certificate",
        "otp",
        "security_card",
        "simple_auth",
        "password",
    }
)

# ── text_snippet 최대 길이 ───────────────────────────────────────────────────

_SNIPPET_MAX_CHARS = 500
_TITLE_MAX_CHARS = 200


def _hash_url(url: str) -> str:
    return "sha256:" + hashlib.sha256(url.encode()).hexdigest()[:16]


def _redact_url(url: str) -> str:
    """URL에서 도메인만 남기고 나머지는 [REDACTED]로 처리한다."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or url
        # path의 첫 segment만 허용
        path_parts = [p for p in (parsed.path or "").split("/") if p]
        short_path = "/" + path_parts[0] if path_parts else ""
        suffix = "/..." if len(path_parts) > 1 else ""
        return f"{scheme}://[REDACTED].{netloc.split('.')[-1] if '.' in netloc else netloc}{short_path}{suffix}"
    except Exception:  # noqa: BLE001 - 읽기 전용 브라우저 런타임 -- URL 리다크션 실패 시 [REDACTED_URL]로 대체(정보 노출 방지 방향), 실행 실패는 DECISION_RUNTIME_NOT_AVAILABLE로 처리(fail-closed)
        return "[REDACTED_URL]"


def _redact_snippet(text: str) -> str:
    """text snippet에서 민감 키워드를 제거하고 길이를 제한한다."""
    redacted = _SNIPPET_SENSITIVE_PATTERNS.sub("[REDACTED]", text)
    return redacted[:_SNIPPET_MAX_CHARS]


def _detect_auth_methods(text: str) -> list[str]:
    """페이지 텍스트에서 인증 방법을 감지한다."""
    detected: list[str] = []
    for pattern, tag in _AUTH_METHOD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE) and tag not in detected:
            detected.append(tag)
    return detected


def _detect_security_requirements(text: str) -> tuple[list[str], list[str]]:
    """보안 요구사항을 감지하고 (requirements, blockers) 튜플을 반환한다."""
    requirements: list[str] = []
    blockers: list[str] = []
    for pattern, tag, is_blocker in _SECURITY_REQ_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if tag not in requirements:
                requirements.append(tag)
            if is_blocker and tag not in blockers:
                blockers.append(tag)
    return requirements, blockers


def evaluate_readonly_browser_permission(payload: dict[str, Any]) -> dict[str, Any]:
    """실행 권한을 평가하고 runtime_decision을 반환한다."""
    operation_type = payload.get("operation_type", "read")
    site_category = payload.get("site_category", "")
    production_mode = payload.get("production_mode", False)

    # production_mode는 항상 BLOCK
    if production_mode:
        return {
            "runtime_decision": DECISION_BLOCK,
            "blocked_reason": "PRODUCTION_MODE_BLOCKED",
            "readonly_execution": False,
            "user_present_required": False,
            "local_agent_required": False,
            "api_required": False,
        }

    # 금지 operation
    if operation_type in _BLOCKED_OPERATIONS:
        return {
            "runtime_decision": DECISION_BLOCK,
            "blocked_reason": f"OPERATION_BLOCKED:{operation_type}",
            "readonly_execution": False,
            "user_present_required": False,
            "local_agent_required": False,
            "api_required": False,
        }

    # operation이 허용 목록에 없으면 BLOCK
    if operation_type not in _ALLOWED_OPERATIONS:
        return {
            "runtime_decision": DECISION_BLOCK,
            "blocked_reason": f"UNKNOWN_OPERATION:{operation_type}",
            "readonly_execution": False,
            "user_present_required": False,
            "local_agent_required": False,
            "api_required": False,
        }

    # API 처리 카테고리
    if site_category in _API_CATEGORIES:
        return {
            "runtime_decision": DECISION_REQUIRE_API,
            "blocked_reason": None,
            "readonly_execution": False,
            "user_present_required": False,
            "local_agent_required": False,
            "api_required": True,
        }

    return {
        "runtime_decision": DECISION_READONLY_ALLOWED,
        "blocked_reason": None,
        "readonly_execution": True,
        "user_present_required": False,
        "local_agent_required": True,
        "api_required": False,
    }


def build_readonly_browser_task(payload: dict[str, Any]) -> dict[str, Any]:
    """read-only 브라우저 작업 객체를 생성한다."""
    permission = evaluate_readonly_browser_permission(payload)
    target_url = payload.get("target_url", "")
    target_url_redacted = payload.get("target_url_redacted") or _redact_url(target_url)

    return {
        "workflow_run_id": payload.get("workflow_run_id"),
        "workflow_id": payload.get("workflow_id"),
        "site_category": payload.get("site_category"),
        "target_url_redacted": target_url_redacted,
        "target_url_hash": _hash_url(target_url) if target_url else None,
        "operation_type": payload.get("operation_type", "read"),
        "user_id": payload.get("user_id"),
        "tenant_id": payload.get("tenant_id"),
        "site_id": payload.get("site_id"),
        "dry_run": payload.get("dry_run", True),
        "production_mode": payload.get("production_mode", False),
        "runtime_decision": permission["runtime_decision"],
        "readonly_execution": permission["readonly_execution"],
        "user_present_required": permission["user_present_required"],
        "local_agent_required": permission["local_agent_required"],
        "api_required": permission["api_required"],
        "blocked_reason": permission["blocked_reason"],
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "audit_required": True,
        "state": STATE_READY,
    }


def execute_readonly_browser_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    실제 read-only 브라우저 작업을 실행한다.

    Playwright가 설치된 환경에서만 실행된다. 미설치 시 RUNTIME_NOT_AVAILABLE을 반환한다.
    어떤 경우에도 click/type/submit/쿠키추출을 수행하지 않는다.
    """
    permission = evaluate_readonly_browser_permission(payload)
    if permission["runtime_decision"] != DECISION_READONLY_ALLOWED:
        return build_readonly_browser_result(
            {
                **payload,
                **permission,
                "page_title": None,
                "text_snippet_redacted": None,
                "detected_auth_methods": [],
                "detected_security_requirements": [],
                "final_url_redacted": None,
                "final_url_hash": None,
            }
        )

    target_url = payload.get("target_url", "")
    if not target_url:
        return build_readonly_browser_result(
            {
                **payload,
                "runtime_decision": DECISION_BLOCK,
                "blocked_reason": "MISSING_TARGET_URL",
                "readonly_execution": False,
                "page_title": None,
                "text_snippet_redacted": None,
                "detected_auth_methods": [],
                "detected_security_requirements": [],
                "final_url_redacted": None,
                "final_url_hash": None,
            }
        )

    try:
        from core.agent_runtime.browser.browser_reader import (  # noqa: F401 - BrowserDependencyMissing은 예외 타입명 문자열 비교(type(exc).__name__)로만 쓰여 심볼 자체는 미사용, 기존 코드(이번 BLE001 작업과 무관)
            BrowserDependencyMissing,
            open_url_readonly,
        )
    except ImportError:
        return build_readonly_browser_result(
            {
                **payload,
                "runtime_decision": DECISION_RUNTIME_NOT_AVAILABLE,
                "blocked_reason": "BROWSER_IMPORT_FAILED",
                "readonly_execution": False,
                "page_title": None,
                "text_snippet_redacted": None,
                "detected_auth_methods": [],
                "detected_security_requirements": [],
                "final_url_redacted": None,
                "final_url_hash": None,
            }
        )

    try:
        raw_result = open_url_readonly(
            target_url,
            wait_until="domcontentloaded",
            timeout_ms=15000,
            max_html_chars=500000,
        )
    except Exception as exc:  # noqa: BLE001 - 읽기 전용 브라우저 런타임 -- URL 리다크션 실패 시 [REDACTED_URL]로 대체(정보 노출 방지 방향), 실행 실패는 DECISION_RUNTIME_NOT_AVAILABLE로 처리(fail-closed)
        err_str = str(exc)
        if "BrowserDependencyMissing" in type(exc).__name__ or "Executable doesn't exist" in err_str:
            decision = DECISION_RUNTIME_NOT_AVAILABLE
            reason = "BROWSER_DEPENDENCY_MISSING"
        else:
            decision = DECISION_FAILED
            reason = "BROWSER_OPEN_FAILED"

        return build_readonly_browser_result(
            {
                **payload,
                "runtime_decision": decision,
                "blocked_reason": reason,
                "readonly_execution": False,
                "page_title": None,
                "text_snippet_redacted": None,
                "detected_auth_methods": [],
                "detected_security_requirements": [],
                "final_url_redacted": None,
                "final_url_hash": None,
            }
        )

    # 결과 분석
    page_title = (raw_result.get("title") or "")[:_TITLE_MAX_CHARS]
    final_url = raw_result.get("final_url") or target_url
    raw_text = raw_result.get("text_snippet") or raw_result.get("body_text") or ""

    # 인증/보안 감지
    combined_text = f"{page_title} {raw_text}"
    detected_auth = _detect_auth_methods(combined_text)
    detected_security, blockers = _detect_security_requirements(combined_text)

    # CAPTCHA 등 blocker 감지 시 BLOCK
    if blockers:
        return build_readonly_browser_result(
            {
                **payload,
                "runtime_decision": DECISION_BLOCK,
                "blocked_reason": f"SECURITY_BLOCKED:{','.join(blockers)}",
                "readonly_execution": True,
                "page_title": page_title,
                "text_snippet_redacted": _redact_snippet(raw_text),
                "detected_auth_methods": detected_auth,
                "detected_security_requirements": detected_security,
                "final_url_redacted": _redact_url(final_url),
                "final_url_hash": _hash_url(final_url),
            }
        )

    # 인증 필요 감지 시 USER_PRESENT_REQUIRED
    user_present_required = bool(set(detected_auth) & _USER_PRESENT_AUTH_METHODS)
    runtime_decision = DECISION_REQUIRE_USER_PRESENT if user_present_required else DECISION_READONLY_ALLOWED

    return build_readonly_browser_result(
        {
            **payload,
            "runtime_decision": runtime_decision,
            "blocked_reason": None,
            "readonly_execution": True,
            "user_present_required": user_present_required,
            "page_title": page_title,
            "text_snippet_redacted": _redact_snippet(raw_text),
            "detected_auth_methods": detected_auth,
            "detected_security_requirements": detected_security,
            "final_url_redacted": _redact_url(final_url),
            "final_url_hash": _hash_url(final_url),
        }
    )


def build_readonly_browser_result(payload: dict[str, Any]) -> dict[str, Any]:
    """결과 dict를 표준 schema로 정규화한다. raw sensitive 필드는 포함하지 않는다."""
    target_url = payload.get("target_url", "")
    return {
        "workflow_run_id": payload.get("workflow_run_id"),
        "site_category": payload.get("site_category"),
        "target_url_redacted": payload.get("target_url_redacted") or _redact_url(target_url),
        "target_url_hash": payload.get("target_url_hash") or (_hash_url(target_url) if target_url else None),
        "final_url_redacted": payload.get("final_url_redacted"),
        "final_url_hash": payload.get("final_url_hash"),
        "page_title": payload.get("page_title"),
        "text_snippet_redacted": payload.get("text_snippet_redacted"),
        "detected_auth_methods": payload.get("detected_auth_methods", []),
        "detected_security_requirements": payload.get("detected_security_requirements", []),
        "user_present_required": payload.get("user_present_required", False),
        "local_agent_required": payload.get("local_agent_required", False),
        "api_required": payload.get("api_required", False),
        "blocked_reason": payload.get("blocked_reason"),
        "runtime_decision": payload.get("runtime_decision", DECISION_BLOCK),
        "readonly_execution": payload.get("readonly_execution", False),
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "audit_required": True,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


def redact_readonly_browser_result(result: dict[str, Any]) -> dict[str, Any]:
    """결과 dict에서 민감 필드를 제거한다."""
    _forbidden = frozenset(
        {
            "target_url",
            "final_url",
            "raw_html",
            "html",
            "screenshot",
            "cookie",
            "session",
            "token",
            "password",
            "otp",
            "certificate_password",
            "localStorage",
            "sessionStorage",
            "internal_policy",
            "audit_raw",
            "secret",
            "api_key",
        }
    )
    return {k: v for k, v in result.items() if k not in _forbidden}


def validate_readonly_browser_result(result: dict[str, Any]) -> list[str]:
    """결과 dict의 필수 필드와 정책 준수를 검증한다."""
    errors: list[str] = []

    required_fields = [
        "runtime_decision",
        "readonly_execution",
        "user_present_required",
        "local_agent_required",
        "api_required",
        "safe_to_dispatch",
        "safe_to_execute",
        "audit_required",
        "created_at",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    if result.get("safe_to_dispatch") is not False:
        errors.append("safe_to_dispatch는 항상 False여야 한다")

    valid_decisions = {
        DECISION_READONLY_ALLOWED,
        DECISION_REQUIRE_USER_PRESENT,
        DECISION_REQUIRE_API,
        DECISION_BLOCK,
        DECISION_RUNTIME_NOT_AVAILABLE,
        DECISION_FAILED,
    }
    decision = result.get("runtime_decision")
    if decision not in valid_decisions:
        errors.append(f"유효하지 않은 runtime_decision: {decision}")

    # raw sensitive 필드가 결과에 없어야 함
    for forbidden in ("target_url", "final_url", "raw_html", "cookie", "session", "token", "password"):
        if forbidden in result:
            errors.append(f"결과에 민감 필드 포함됨: {forbidden}")

    return errors
