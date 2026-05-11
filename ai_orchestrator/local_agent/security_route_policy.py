"""Security Route Policy — 보안프로그램 사이트 접속 시 경로 분류."""
from __future__ import annotations

from typing import Any

# 라우팅 상태
ROUTE_OFFICIAL_API_OR_MOBILE = "OFFICIAL_API_OR_MOBILE_ROUTE"
ROUTE_ALREADY_INSTALLED = "ALREADY_INSTALLED"
ROUTE_INSTALL_REQUIRED = "INSTALL_REQUIRED"
ROUTE_TRUSTED_INSTALLER_AVAILABLE = "TRUSTED_INSTALLER_AVAILABLE"
ROUTE_FIRST_TIME_USER_APPROVAL_REQUIRED = "FIRST_TIME_USER_APPROVAL_REQUIRED"
ROUTE_USER_UAC_REQUIRED = "USER_UAC_REQUIRED"
ROUTE_RETRY_ORIGINAL_TASK_READY = "RETRY_ORIGINAL_TASK_READY"
ROUTE_BLOCKED = "BLOCKED"

# USER_DIRECT 등급 action (설치 후에도 사용자 직접)
_USER_DIRECT_ACTIONS = frozenset((
    "payment", "transfer", "bid", "e_signature",
    "final_submit", "결제", "송금", "투찰", "전자서명",
))


def classify_route(
    has_alternative_route: bool,
    is_already_installed: bool,
    requires_security_program: bool,
    has_trusted_installer: bool,
    user_approved: bool,
    needs_uac: bool,
    install_completed: bool = False,
) -> dict[str, Any]:
    """라우팅 상태를 결정한다."""
    if install_completed:
        return _result(ROUTE_RETRY_ORIGINAL_TASK_READY,
                       "설치 완료 — 원래 작업 재개 가능", grade="AUTO_ALLOWED")

    if has_alternative_route:
        return _result(ROUTE_OFFICIAL_API_OR_MOBILE,
                       "공식 API/모바일/무설치 경로 사용 가능", grade="AUTO_ALLOWED")

    if is_already_installed:
        return _result(ROUTE_ALREADY_INSTALLED,
                       "보안프로그램 이미 설치됨 — 설치 없이 재접속", grade="AUTO_ALLOWED")

    if not requires_security_program:
        return _result(ROUTE_ALREADY_INSTALLED,
                       "보안프로그램 불필요", grade="AUTO_ALLOWED")

    if has_trusted_installer:
        if needs_uac:
            return _result(ROUTE_USER_UAC_REQUIRED,
                           "신뢰된 설치파일 — UAC 사용자 직접 승인 필요",
                           grade="USER_DIRECT_REQUIRED")
        return _result(ROUTE_TRUSTED_INSTALLER_AVAILABLE,
                       "신뢰된 설치파일 — 재실행/업데이트 가능",
                       grade="USER_DELEGATED_PERMISSION_REQUIRED")

    if not user_approved:
        return _result(ROUTE_FIRST_TIME_USER_APPROVAL_REQUIRED,
                       "최초 1회 사용자 승인 필요",
                       grade="USER_DELEGATED_PERMISSION_REQUIRED")

    if needs_uac:
        return _result(ROUTE_USER_UAC_REQUIRED,
                       "UAC 사용자 직접 승인 필요",
                       grade="USER_DIRECT_REQUIRED")

    return _result(ROUTE_INSTALL_REQUIRED,
                   "설치 진행 가능",
                   grade="USER_DELEGATED_PERMISSION_REQUIRED")


def is_user_direct_action(action: str) -> bool:
    """결제/송금/투찰/전자서명 등 USER_DIRECT_REQUIRED action 여부."""
    if not action:
        return False
    lower = action.lower()
    return any(k in lower for k in _USER_DIRECT_ACTIONS)


def _result(route: str, message: str, grade: str) -> dict[str, Any]:
    return {
        "route": route,
        "message_ko": message,
        "grade": grade,
        "server_browser_used": False,
    }
