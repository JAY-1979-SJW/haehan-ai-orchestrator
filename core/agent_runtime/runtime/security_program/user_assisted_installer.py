"""User Assisted Installer — 사용자 직접 설치 모드 (AI는 자동 실행하지 않음)."""
from __future__ import annotations

import uuid
from typing import Any

# 상태
STATUS_SECURITY_PROGRAM_REQUIRED = "SECURITY_PROGRAM_REQUIRED"
STATUS_INSTALLER_CANDIDATE_FOUND = "INSTALLER_CANDIDATE_FOUND"
STATUS_INSTALLER_DOWNLOADED = "INSTALLER_DOWNLOADED"
STATUS_INSTALLER_VERIFIED = "INSTALLER_VERIFIED"
STATUS_WAITING_USER_INSTALL_CLICK = "WAITING_USER_INSTALL_CLICK"
STATUS_WAITING_USER_UAC = "WAITING_USER_UAC"
STATUS_USER_INSTALL_IN_PROGRESS = "USER_INSTALL_IN_PROGRESS"
STATUS_INSTALL_COMPLETED_DETECTED = "INSTALL_COMPLETED_DETECTED"
STATUS_INSTALL_NOT_DETECTED = "INSTALL_NOT_DETECTED"
STATUS_RETRY_ORIGINAL_TASK_READY = "RETRY_ORIGINAL_TASK_READY"
STATUS_ORIGINAL_TASK_RESUMED = "ORIGINAL_TASK_RESUMED"

_USER_GUIDE_KO = (
    "공식 설치파일을 다운로드하고 검증했습니다.\n"
    "탐색기에서 선택된 설치파일을 더블클릭해 설치를 진행해 주세요.\n"
    "UAC/관리자 권한 창이 뜨면 사용자가 직접 승인해야 합니다.\n"
    "설치가 끝나면 이 화면에서 '설치 완료 확인'을 눌러 주세요.\n"
    "이후 앱이 자동으로 사이트에 재접속합니다."
)

_SAFE_FIELDS = (
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
)


def prepare_user_install(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    installer_safe_name: str,
    source_host: str,
    sha256: str,
    signature_status: str,
    file_size_bytes: int | None = None,
    signer_subject: str = "",
    target_domain: str = "",
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    검증된 설치파일에 대해 사용자 설치 대기 상태를 생성한다.
    AI는 절대 자동 실행하지 않는다.

    Returns:
        WAITING_USER_INSTALL_CLICK 상태의 safe result
    """
    if signature_status != "Valid":
        return _safe_result(
            task_id=task_id or str(uuid.uuid4()),
            status="SIGNATURE_INVALID",
            installer_safe_name=installer_safe_name,
            source_host=source_host,
            sha256=sha256,
            signature_status=signature_status,
            message=f"서명 상태가 Valid 아님: {signature_status}. 설치 거부.",
        )

    return _safe_result(
        task_id=task_id or str(uuid.uuid4()),
        status=STATUS_WAITING_USER_INSTALL_CLICK,
        installer_safe_name=_safe_name(installer_safe_name),
        source_host=source_host,
        sha256=sha256.lower(),
        signature_status=signature_status,
        signer_subject=signer_subject,
        file_size_bytes=file_size_bytes,
        target_domain=target_domain,
        message=_USER_GUIDE_KO,
        auto_execute=False,  # AI는 절대 실행하지 않음
    )


def confirm_user_completed(
    task_id: str,
    installer_safe_name: str,
    target_domain: str = "",
) -> dict[str, Any]:
    """사용자가 '설치 완료 확인' 버튼을 클릭한 상태."""
    return _safe_result(
        task_id=task_id,
        status=STATUS_USER_INSTALL_IN_PROGRESS,
        installer_safe_name=_safe_name(installer_safe_name),
        target_domain=target_domain,
        message="사용자가 설치 완료를 보고했습니다. headed 브라우저로 재접속을 시작합니다.",
    )


def get_status_grade(status: str) -> str:
    """상태별 실행 등급."""
    if status in (STATUS_WAITING_USER_UAC, STATUS_WAITING_USER_INSTALL_CLICK):
        return "USER_DIRECT_REQUIRED"
    if status in (
        STATUS_INSTALLER_CANDIDATE_FOUND,
        STATUS_INSTALLER_DOWNLOADED,
        STATUS_INSTALLER_VERIFIED,
        STATUS_INSTALL_COMPLETED_DETECTED,
        STATUS_RETRY_ORIGINAL_TASK_READY,
        STATUS_ORIGINAL_TASK_RESUMED,
    ):
        return "AUTO_ALLOWED"
    return "USER_DELEGATED_PERMISSION_REQUIRED"


def _safe_name(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


def _safe_result(**fields) -> dict[str, Any]:
    """safe field 항상 False, local full path 등 민감 필드 미포함."""
    result: dict[str, Any] = {}
    for k, v in fields.items():
        # 민감 필드 차단
        if k.lower() in ("local_path", "full_path", "installer_path"):
            continue
        if v is not None:
            result[k] = v
    for f in _SAFE_FIELDS:
        result[f] = False
    return result
