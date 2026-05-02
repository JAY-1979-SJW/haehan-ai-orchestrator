"""Docker Desktop 전용 설치 실행 엔진 (1D: 단일 프로그램 전용)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import errors as _err


DOCKER_OFFICIAL_URL = "https://www.docker.com/products/docker-desktop/"

DOCKER_INSTALLER_ALLOWED_NAMES = frozenset({
    'docker desktop installer.exe',
    'dockerdesktopinstaller.exe',
})


@dataclass(frozen=True)
class DockerInstallResult:
    """Docker 설치 결과."""
    status: str
    docker_cli_installed: bool
    docker_compose_installed: bool
    reboot_may_be_required: bool
    next_step: str
    official_url: str = DOCKER_OFFICIAL_URL
    error: Optional[str] = None


class DockerInstallerValidator:
    """Docker 설치파일 검증기."""

    def validate_path(self, installer_path: str) -> tuple[bool, Optional[str]]:
        """설치파일 경로 검증.

        Args:
            installer_path: 설치파일 경로

        Returns:
            (success, error_code)
        """
        # 경로 없으면
        if not installer_path or not isinstance(installer_path, str):
            return False, _err.INSTALL_PROGRAM_ID_REQUIRED

        # 확장자 확인
        if not installer_path.lower().endswith('.exe'):
            return False, 'docker_installer_invalid_extension'

        # 파일명 확인
        filename = Path(installer_path).name.lower()
        if filename not in DOCKER_INSTALLER_ALLOWED_NAMES:
            return False, 'docker_installer_name_not_allowed'

        # 파일 존재 확인
        if not Path(installer_path).exists():
            return False, _err.FILE_NOT_FOUND

        # 파일 타입 확인
        if not Path(installer_path).is_file():
            return False, 'docker_installer_not_file'

        return True, None


class DockerInstaller:
    """Docker Desktop 전용 설치 엔진."""

    def __init__(self):
        """Docker 설치 엔진 초기화."""
        self.validator = DockerInstallerValidator()

    def check_status(self) -> dict:
        """Docker 현재 설치 상태 확인.

        Returns:
            {'docker_cli_installed': bool, 'docker_compose_installed': bool, ...}
        """
        docker_installed = False
        docker_compose_installed = False

        # docker --version 확인
        try:
            result = subprocess.run(
                ['docker', '--version'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            docker_installed = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            docker_installed = False

        # docker compose version 확인
        try:
            result = subprocess.run(
                ['docker', 'compose', 'version'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            docker_compose_installed = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            docker_compose_installed = False

        return {
            'docker_cli_installed': docker_installed,
            'docker_compose_installed': docker_compose_installed,
        }

    def run_install(
        self,
        installer_path: Optional[str],
        approval_token: str,
        user_confirmed_install: bool,
    ) -> DockerInstallResult:
        """Docker 설치 실행.

        Args:
            installer_path: 설치파일 경로 (None이면 B안)
            approval_token: 사용자 승인 토큰
            user_confirmed_install: 사용자 확인 플래그

        Returns:
            DockerInstallResult
        """
        # 승인 확인
        if not approval_token or not isinstance(approval_token, str):
            return DockerInstallResult(
                status='install_failed',
                docker_cli_installed=False,
                docker_compose_installed=False,
                reboot_may_be_required=False,
                next_step='승인 토큰 확인 필요',
                error=_err.INSTALL_APPROVAL_REQUIRED,
            )

        if not user_confirmed_install:
            return DockerInstallResult(
                status='install_failed',
                docker_cli_installed=False,
                docker_compose_installed=False,
                reboot_may_be_required=False,
                next_step='사용자 확인 필요',
                error='docker_user_confirmation_required',
            )

        # 현재 상태 확인
        status_before = self.check_status()
        if status_before['docker_cli_installed']:
            return DockerInstallResult(
                status='already_installed',
                docker_cli_installed=True,
                docker_compose_installed=status_before['docker_compose_installed'],
                reboot_may_be_required=False,
                next_step='Docker은 이미 설치되어 있습니다.',
            )

        # 설치파일 경로 없음 → B안 (공식 URL 안내)
        if not installer_path:
            return DockerInstallResult(
                status='download_required',
                docker_cli_installed=False,
                docker_compose_installed=False,
                reboot_may_be_required=False,
                next_step=f'Docker Desktop을 다운로드하여 설치하세요.',
            )

        # 설치파일 검증
        valid, error_code = self.validator.validate_path(installer_path)
        if not valid:
            return DockerInstallResult(
                status='install_failed',
                docker_cli_installed=False,
                docker_compose_installed=False,
                reboot_may_be_required=False,
                next_step='설치파일 검증 실패',
                error=error_code or 'docker_installer_validation_failed',
            )

        # A안: 실제 설치 실행 (Start-Process -Verb RunAs)
        success, error = self._execute_installer(installer_path)

        # 설치 후 상태 확인
        status_after = self.check_status()

        # 설치 실패 판정
        if not status_after['docker_cli_installed'] and success:
            # 설치 명령 성공했지만 docker 실행 불가 → 재부팅 필요 가능
            return DockerInstallResult(
                status='install_failed',
                docker_cli_installed=False,
                docker_compose_installed=False,
                reboot_may_be_required=True,
                next_step='Docker 설치 후 시스템 재부팅이 필요할 수 있습니다.',
                error='docker_requires_reboot',
            )

        # 설치 성공
        if status_after['docker_cli_installed']:
            return DockerInstallResult(
                status='install_completed',
                docker_cli_installed=True,
                docker_compose_installed=status_after['docker_compose_installed'],
                reboot_may_be_required=False,
                next_step='Docker Desktop 설치가 완료되었습니다.',
            )

        # 설치 실패 (unknown)
        return DockerInstallResult(
            status='install_failed',
            docker_cli_installed=False,
            docker_compose_installed=False,
            reboot_may_be_required=False,
            next_step='Docker 설치 실패. 수동 설치를 권장합니다.',
            error=error or 'docker_install_unknown_error',
        )

    def _execute_installer(self, installer_path: str) -> tuple[bool, Optional[str]]:
        """설치파일 실행 (A안: Windows Start-Process -Verb RunAs).

        Args:
            installer_path: 설치파일 경로

        Returns:
            (success, error_message)

        Note:
            UAC 팝업은 사용자가 직접 승인합니다.
            관리자 비밀번호 저장/전달 없음.
        """
        try:
            # PowerShell로 Start-Process -Verb RunAs 실행
            # UAC 팝업 발생 → 사용자가 직접 승인
            result = subprocess.run(
                [
                    'powershell',
                    '-Command',
                    f'Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait',
                ],
                timeout=600,  # 최대 10분 대기
                capture_output=True,
            )

            # 0: 설치 완료
            # 그 외: 설치 취소 또는 오류
            return result.returncode == 0, None

        except subprocess.TimeoutExpired:
            return False, 'docker_install_timeout'
        except Exception as e:
            return False, f'docker_install_error:{type(e).__name__}'

    def verify_after_install(self) -> dict:
        """설치 후 검증.

        Returns:
            검증 결과 dict
        """
        return self.check_status()
