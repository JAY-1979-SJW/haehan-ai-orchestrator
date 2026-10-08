"""Installer Folder Presenter — Windows 탐색기에서 설치파일 위치 표시."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)

# 결과 상태
PRESENT_OPENED = "EXPLORER_OPENED"
PRESENT_FAILED = "EXPLORER_FAILED"
PRESENT_NOT_SUPPORTED = "PLATFORM_NOT_SUPPORTED"


def build_explorer_command(local_path: str) -> list[str]:
    """
    탐색기를 열어 설치파일을 선택 상태로 표시하는 명령을 구성한다.
    실제 실행은 present_installer_in_explorer가 수행.
    """
    if not local_path:
        raise ValueError("경로가 비어 있습니다.")
    # /select,<path> 형식 사용 — 파일 선택 표시
    return ["explorer.exe", f"/select,{local_path}"]


def present_installer_in_explorer(
    local_path: str,
    installer_safe_name: str,
    target_domain: str = "",
    task_id: str = "",
) -> dict[str, Any]:
    """
    탐색기에서 설치파일 선택 상태로 표시한다.
    local_path는 함수 내부에서만 사용 — 결과에는 포함되지 않는다.
    """
    if not sys.platform.startswith("win"):
        return _result(
            status=PRESENT_NOT_SUPPORTED,
            installer_safe_name=_safe_name(installer_safe_name),
            target_domain=target_domain,
            task_id=task_id,
            message="Windows 외 플랫폼은 탐색기 표시 미지원.",
            opened=False,
        )

    if not Path(local_path).exists():
        return _result(
            status=PRESENT_FAILED,
            installer_safe_name=_safe_name(installer_safe_name),
            target_domain=target_domain,
            task_id=task_id,
            message="설치파일이 존재하지 않습니다. 다시 다운로드해 주세요.",
            opened=False,
        )

    try:
        # explorer.exe /select,<path> — 파일 선택 표시
        # silent install/runas 사용 안 함
        subprocess.Popen(
            ["explorer.exe", f"/select,{local_path}"],
            shell=False,
        )
        return _result(
            status=PRESENT_OPENED,
            installer_safe_name=_safe_name(installer_safe_name),
            target_domain=target_domain,
            task_id=task_id,
            message=(
                f"탐색기에 설치파일({_safe_name(installer_safe_name)})이 선택된 상태로 표시되었습니다. "
                "사용자가 직접 더블클릭하여 설치를 진행해 주세요."
            ),
            opened=True,
        )
    except Exception as e:  # noqa: BLE001 - 설치파일 폴더 열기 실패 시 PRESENT_FAILED 상태로 폴백 — 전체 경로는 결과에 포함하지 않음(코드 내 주석 명시), fail-closed
        # 실패 시 fallback: 경로 안내 (full path는 결과에 포함하지 않음)
        return _result(
            status=PRESENT_FAILED,
            installer_safe_name=_safe_name(installer_safe_name),
            target_domain=target_domain,
            task_id=task_id,
            message=f"탐색기 열기 실패: {type(e).__name__}. 다운로드 폴더에서 직접 찾아 주세요.",
            opened=False,
        )


def _safe_name(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


def _result(**fields) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in fields.items():
        if k.lower() in ("local_path", "full_path", "installer_path"):
            continue
        if v is not None:
            result[k] = v
    for f in _SAFE_FIELDS:
        result[f] = False
    return result
