"""Local Security Installer Runner — 사용자 승인 후 설치 파일 실행을 보조한다."""

from __future__ import annotations

import uuid
from typing import Any

# 설치 상태 상수
STATUS_INSTALL_PERMISSION_REQUIRED = "INSTALL_PERMISSION_REQUIRED"
STATUS_INSTALLER_DOWNLOADED = "INSTALLER_DOWNLOADED"
STATUS_INSTALLER_VERIFIED = "INSTALLER_VERIFIED"
STATUS_WAITING_USER_UAC = "WAITING_USER_UAC"
STATUS_INSTALL_RUNNING = "INSTALL_RUNNING"
STATUS_INSTALL_COMPLETED = "INSTALL_COMPLETED"
STATUS_INSTALL_FAILED = "INSTALL_FAILED"
STATUS_RESTART_BROWSER_REQUIRED = "RESTART_BROWSER_REQUIRED"
STATUS_RETRY_ORIGINAL_TASK_READY = "RETRY_ORIGINAL_TASK_READY"

# 금지 실행 등급
GRADE_BLOCKED = "BLOCKED"

# 금지 action 목록
_BLOCKED_ACTIONS = frozenset(
    (
        "bypass_security_program",
        "disable_security_module",
        "kill_security_process",
        "auto_uac_approval",
        "bypass_uac",
        "silent_install_auto",
        "bypass_captcha",
        "export_cookie",
        "export_session",
        "export_storage_state",
        "save_password",
        "save_otp",
        "save_cert_password",
        "access_npki",
        "access_cert_file",
        "auto_payment",
        "auto_transfer",
        "auto_bid",
        "auto_sign",
    )
)

# 설치 완료 감지 프로세스 힌트 (실제 실행은 사용자가 직접)
_INSTALL_COMPLETE_HINTS = (
    "설치가 완료",
    "설치 완료",
    "installation complete",
    "successfully installed",
    "설치되었습니다",
)


def check_action_allowed(action: str) -> dict[str, Any]:
    """action이 허용 가능한지 확인한다."""
    if action in _BLOCKED_ACTIONS:
        return {
            "allowed": False,
            "grade": GRADE_BLOCKED,
            "reason": f"금지된 action: {action}",
        }
    return {
        "allowed": True,
        "grade": "USER_DELEGATED_PERMISSION_REQUIRED",
        "reason": None,
    }


def prepare_install(
    installer_candidate: dict[str, Any],
    has_permission: bool = False,
    policy_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    설치 준비 상태를 반환한다. 실제 실행은 사용자 승인 후.

    Returns:
        {
            "task_id": str,
            "status": STATUS_*,
            "installer_safe_name": str,
            "source_host": str,
            "requires_uac": bool,
            "user_message_ko": str,
            "executable": bool,
            "server_browser_used": False,
        }
    """
    task_id = str(uuid.uuid4())
    filename = installer_candidate.get("filename", "")
    source_host = installer_candidate.get("source_host", "")

    if not installer_candidate.get("allowed", False):
        return {
            "task_id": task_id,
            "status": STATUS_INSTALL_FAILED,
            "installer_safe_name": filename,
            "source_host": source_host,
            "requires_uac": False,
            "user_message_ko": f"설치 후보가 차단되었습니다: {installer_candidate.get('block_reason', '')}",
            "executable": False,
            "server_browser_used": False,
        }

    if not has_permission:
        return {
            "task_id": task_id,
            "status": STATUS_INSTALL_PERMISSION_REQUIRED,
            "installer_safe_name": filename,
            "source_host": source_host,
            "requires_uac": True,
            "user_message_ko": (
                f"보안프로그램({filename}) 설치를 위해 사용자 승인이 필요합니다. 승인 후 설치를 진행하겠습니다."
            ),
            "executable": False,
            "server_browser_used": False,
        }

    requires_uac = policy_result.get("requires_uac", True) if policy_result else True

    if requires_uac:
        return {
            "task_id": task_id,
            "status": STATUS_WAITING_USER_UAC,
            "installer_safe_name": filename,
            "source_host": source_host,
            "requires_uac": True,
            "user_message_ko": (
                f"설치 파일({filename})을 실행하려면 UAC(관리자 권한) 승인이 필요합니다. "
                "화면에 나타나는 UAC 창에서 '예'를 직접 클릭해 주세요."
            ),
            "executable": True,
            "server_browser_used": False,
        }

    return {
        "task_id": task_id,
        "status": STATUS_INSTALLER_VERIFIED,
        "installer_safe_name": filename,
        "source_host": source_host,
        "requires_uac": False,
        "user_message_ko": f"설치 파일({filename}) 검증 완료. 설치를 진행합니다.",
        "executable": True,
        "server_browser_used": False,
    }


def check_install_completed(page_data: dict[str, Any]) -> dict[str, Any]:
    """
    설치 완료 여부를 페이지 텍스트로 확인한다.
    (실제 프로세스 감지 없이 페이지 기반만 확인)
    """
    text = page_data.get("text_content", "") + " " + page_data.get("title", "")
    completed = any(hint in text for hint in _INSTALL_COMPLETE_HINTS)

    # 브라우저 재시작 필요 여부
    restart_hints = ("브라우저 재시작", "브라우저를 다시", "재시작 후", "restart browser")
    restart_required = any(h in text for h in restart_hints)

    if completed:
        status = STATUS_RESTART_BROWSER_REQUIRED if restart_required else STATUS_INSTALL_COMPLETED
    else:
        status = STATUS_INSTALL_RUNNING

    return {
        "status": status,
        "install_completed": completed,
        "restart_browser_required": restart_required,
        "retry_original_task_ready": completed and not restart_required,
        "server_browser_used": False,
    }


def get_retry_ready_result(original_task_id: str) -> dict[str, Any]:
    """설치 완료 후 원래 task 재시도 준비 결과."""
    return {
        "status": STATUS_RETRY_ORIGINAL_TASK_READY,
        "original_task_id": original_task_id,
        "user_message_ko": "보안프로그램 설치가 완료되었습니다. 원래 작업을 재시도합니다.",
        "server_browser_used": False,
    }
