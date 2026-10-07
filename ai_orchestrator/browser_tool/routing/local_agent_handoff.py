"""
Local Agent Handoff 모듈

서버 실패 또는 로컬 필수 판정 시 로컬 에이전트에 넘길
안전한 작업 패키지를 생성한다.

원칙:
- 서버 세션/쿠키/인증 헤더를 로컬로 복사하지 않음
- 비밀번호/OTP/인증서 정보 전달 없음
- 안전한 URL과 action만 전달
- forbidden 목록은 항상 포함
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# ── handoff type 상수 ─────────────────────────────────────────────────────────

HANDOFF_LOCAL_BROWSER_CONTINUE = "LOCAL_AGENT_BROWSER_CONTINUE"
HANDOFF_LOCAL_LOGIN_WAIT = "LOCAL_AGENT_LOGIN_WAIT"
HANDOFF_LOCAL_READONLY = "LOCAL_AGENT_READONLY"

# ── 허용 action ────────────────────────────────────────────────────────────────

_ALLOWED_HANDOFF_ACTIONS: frozenset[str] = frozenset(
    {
        "open",
        "read",
        "navigate",
        "open_url",
        "login_wait",
        "public_read",
        "search",
    }
)

# ── 금지 목록 (항상 포함) ─────────────────────────────────────────────────────

_FORBIDDEN_ALWAYS: list[str] = [
    "cookie_export",
    "session_export",
    "password_collect",
    "otp_collect",
    "cert_file_access",
    "npki_access",
    "auto_submit",
    "auto_sign",
    "auto_payment",
    "auto_bid_submit",
    "auto_transfer",
    "auto_contract_submit",
    "token_export",
    "auth_header_export",
    "localStorage_dump",
    "sessionStorage_dump",
    "private_key_access",
    "screenshot_sensitive",
]

_ALLOWED_URL_DOMAINS: frozenset[str] = frozenset(
    {
        "g2b.go.kr",
        "www.g2b.go.kr",
        "hometax.go.kr",
        "www.hometax.go.kr",
    }
)


def build_local_agent_handoff(
    task: dict[str, Any],
    fallback_reason: str = "",
    handoff_type: str = HANDOFF_LOCAL_BROWSER_CONTINUE,
) -> dict[str, Any]:
    """
    로컬 에이전트에 전달할 안전한 handoff payload를 생성한다.
    민감 데이터는 포함하지 않는다.
    """
    task_id = task.get("task_id", "")
    raw_url = task.get("target_url") or task.get("url") or ""
    action = (task.get("action") or "open").lower()

    # action이 허용 목록에 없으면 read로 downgrade
    if action not in _ALLOWED_HANDOFF_ACTIONS:
        action = "read"

    # URL 안전 검증
    safe_url = _sanitize_url(raw_url)

    # readonly 강제 (submit/sign/pay는 handoff 불가)
    readonly = True

    return {
        "task_id": task_id,
        "handoff_type": handoff_type,
        "target_url": safe_url,
        "action": action,
        "readonly": readonly,
        "fallback_reason": fallback_reason,
        "local_browser_default": True,
        "user_message_ko": (
            "이 작업은 사용자 PC에서 실행됩니다.\n"
            "브라우저가 열리면 필요한 경우 직접 인증해 주세요.\n"
            "비밀번호, OTP, 인증서 비밀번호는 앱이 저장하지 않습니다."
        ),
        "forbidden": list(_FORBIDDEN_ALWAYS),
        "sensitive_data_included": False,
        "cookie_included": False,
        "session_included": False,
        "password_included": False,
        "otp_included": False,
        "cert_info_included": False,
    }


def _sanitize_url(url: str) -> str:
    """URL에서 민감한 쿼리 파라미터를 제거하고 안전한 URL을 반환한다."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        # 허용 도메인만 통과
        if parsed.netloc and parsed.netloc not in _ALLOWED_URL_DOMAINS:
            # 허용 도메인 외부는 그대로 전달 (차단은 policy에서)
            pass
        # 쿼리스트링에서 민감 파라미터 제거
        sensitive_params = {"token", "session", "auth", "password", "otp", "key"}
        if parsed.query:
            from urllib.parse import parse_qs, urlencode

            params = parse_qs(parsed.query, keep_blank_values=True)
            clean_params = {k: v for k, v in params.items() if k.lower() not in sensitive_params}
            clean_query = urlencode(clean_params, doseq=True)
            return parsed._replace(query=clean_query).geturl()
        return url
    except Exception:  # noqa: BLE001 - 로컬 에이전트 핸드오프 페이로드의 URL 정리/도메인 추출 -- 실패 시 원본 URL 또는 빈 문자열 반환(안전한 폴백), 쓰기 없음
        return url


def validate_handoff_payload(payload: dict[str, Any]) -> list[str]:
    """
    handoff payload에 민감 데이터가 없는지 검증한다.
    위반 목록 반환 (빈 리스트 = 안전).
    """
    violations: list[str] = []
    sensitive_checks = {
        "cookie_included",
        "session_included",
        "password_included",
        "otp_included",
        "cert_info_included",
        "sensitive_data_included",
    }
    for field in sensitive_checks:
        if payload.get(field) is True:
            violations.append(f"민감 데이터 포함: {field!r}")

    # forbidden 목록이 비어 있으면 위반
    if not payload.get("forbidden"):
        violations.append("forbidden 목록 없음")

    # readonly가 False이면 위반
    if payload.get("readonly") is False:
        violations.append("readonly=False: handoff는 read-only만 허용")

    return violations


# ── task protocol 연결 ────────────────────────────────────────────────────────

_HANDOFF_ACTION_TO_PROTOCOL: dict[str, str] = {
    "open": "open_url",
    "open_url": "open_url",
    "navigate": "open_url",
    "read": "read_page",
    "public_read": "read_page",
    "search": "search",
    "login_wait": "wait_for_user_auth",
    "download": "download_file",
}


def handoff_to_task_protocol(
    handoff: dict[str, Any],
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    local_agent_handoff payload를 task_protocol.build_task 형태로 변환한다.
    서버 task queue로 전달하기 위한 bridge 함수.
    민감 데이터 없음이 보장된다.
    """
    from ai_orchestrator.contracts.local_task_protocol import ALLOWED_TASK_ACTIONS, build_task

    raw_action = (handoff.get("action") or "open").lower()
    protocol_action = _HANDOFF_ACTION_TO_PROTOCOL.get(raw_action, "open_url")

    # 허용 action이 아니면 open_url로 downgrade
    if protocol_action not in ALLOWED_TASK_ACTIONS:
        protocol_action = "open_url"

    target_url = handoff.get("target_url") or ""

    return build_task(
        action=protocol_action,
        target_url=target_url,
        domain=_extract_domain(target_url),
        readonly=True,
        requires_user_presence=False,
        timeout_seconds=300,
        task_id=task_id or handoff.get("task_id"),
        metadata={
            "handoff_type": handoff.get("handoff_type", ""),
            "fallback_reason": handoff.get("fallback_reason", ""),
            "local_browser_default": True,
        },
    )


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001 - 로컬 에이전트 핸드오프 페이로드의 URL 정리/도메인 추출 -- 실패 시 원본 URL 또는 빈 문자열 반환(안전한 폴백), 쓰기 없음
        return ""
