"""Windows 선행조건 활성화 실행 엔진 (WSL, VirtualMachinePlatform 등).

사용자 승인형 UAC를 통한 Windows 기능 활성화.
자동 재부팅 금지, 관리자 비밀번호 저장 금지.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass(frozen=True)
class WindowsPrereqRequest:
    """Windows 선행조건 활성화 요청."""
    target_prereq: str  # 'wsl2', ...
    approval_token: str
    user_confirmed_windows_feature_change: bool = False
    dry_run: bool = True


@dataclass(frozen=True)
class WindowsPrereqResult:
    """Windows 선행조건 활성화 결과."""
    ok: bool
    dry_run: bool
    target_prereq: str
    status: str  # 'pending', 'enabled', 'requires_reboot', 'failed'
    planned_steps: List[str]
    verification_commands: List[str]
    reboot_required: bool = False
    error: Optional[str] = None
    message: str = ''


class WindowsFeatureExecutor:
    """Windows 기능 활성화 실행 엔진."""

    def execute(self, request: WindowsPrereqRequest) -> WindowsPrereqResult:
        """Windows 선행조건 활성화 요청 처리.

        Args:
            request: WindowsPrereqRequest

        Returns:
            WindowsPrereqResult
        """
        # 요청 검증
        if not request.approval_token:
            return WindowsPrereqResult(
                ok=False,
                dry_run=request.dry_run,
                target_prereq=request.target_prereq,
                status='pending',
                planned_steps=[],
                verification_commands=[],
                error='approval_token_required',
                message='승인 토큰이 필요합니다.',
            )

        if not request.user_confirmed_windows_feature_change:
            return WindowsPrereqResult(
                ok=False,
                dry_run=request.dry_run,
                target_prereq=request.target_prereq,
                status='pending',
                planned_steps=[],
                verification_commands=[],
                error='user_confirmation_required',
                message='사용자 확인이 필요합니다.',
            )

        # target_prereq 검증
        if request.target_prereq != 'wsl2':
            return WindowsPrereqResult(
                ok=False,
                dry_run=request.dry_run,
                target_prereq=request.target_prereq,
                status='pending',
                planned_steps=[],
                verification_commands=[],
                error='unsupported_target_prereq',
                message=f'지원하지 않는 대상: {request.target_prereq}',
            )

        # dry_run=true: 계획만 반환
        if request.dry_run:
            return self._get_dry_run_plan(request)

        # dry_run=false: 실제 실행
        return self._execute_windows_feature(request)

    def _get_dry_run_plan(self, request: WindowsPrereqRequest) -> WindowsPrereqResult:
        """WSL 활성화 계획 생성 (dry_run).

        Args:
            request: WindowsPrereqRequest

        Returns:
            WindowsPrereqResult (planned_steps 포함)
        """
        if request.target_prereq == 'wsl2':
            planned_steps = [
                '1단계: 관리자 권한 확인 (UAC 팝업)',
                '2단계: PowerShell에서 WSL 설치 명령 실행: wsl --install',
                '3단계: 시스템 재부팅 (필요 시)',
                '4단계: WSL 버전 확인: wsl --version',
            ]

            verification_commands = [
                'wsl --version',
                'wsl --status',
                'wsl -l -v',
                'Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux',
                'Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform',
            ]

            return WindowsPrereqResult(
                ok=True,
                dry_run=True,
                target_prereq=request.target_prereq,
                status='pending',
                planned_steps=planned_steps,
                verification_commands=verification_commands,
                reboot_required=False,
                message='WSL 활성화 계획이 준비되었습니다.',
            )

        return WindowsPrereqResult(
            ok=False,
            dry_run=True,
            target_prereq=request.target_prereq,
            status='pending',
            planned_steps=[],
            verification_commands=[],
            error='unsupported_target_prereq',
            message=f'지원하지 않는 대상: {request.target_prereq}',
        )

    def _execute_windows_feature(self, request: WindowsPrereqRequest) -> WindowsPrereqResult:
        """Windows 기능 활성화 실행 (실제 실행).

        Args:
            request: WindowsPrereqRequest

        Returns:
            WindowsPrereqResult
        """
        if request.target_prereq == 'wsl2':
            return self._execute_wsl_install(request)

        return WindowsPrereqResult(
            ok=False,
            dry_run=False,
            target_prereq=request.target_prereq,
            status='failed',
            planned_steps=[],
            verification_commands=[],
            error='unsupported_target_prereq',
            message=f'지원하지 않는 대상: {request.target_prereq}',
        )

    def _execute_wsl_install(self, request: WindowsPrereqRequest) -> WindowsPrereqResult:
        """WSL 설치 실행 (관리자 UAC).

        Args:
            request: WindowsPrereqRequest

        Returns:
            WindowsPrereqResult
        """
        try:
            # wsl --install 명령 실행 (관리자 UAC)
            cmd = 'wsl --install --no-launch'
            powershell_cmd = f'Start-Process powershell -Verb RunAs -Wait -ArgumentList "-Command", "{cmd}"'

            result = subprocess.run(
                [
                    'powershell',
                    '-Command',
                    powershell_cmd,
                ],
                timeout=600,
                capture_output=True,
            )

            # 명령 실행 결과 검증
            if result.returncode == 0:
                return WindowsPrereqResult(
                    ok=True,
                    dry_run=False,
                    target_prereq=request.target_prereq,
                    status='requires_reboot',
                    planned_steps=[],
                    verification_commands=['wsl --version', 'wsl --status'],
                    reboot_required=True,
                    message='WSL 설치가 실행되었습니다. 시스템 재부팅이 필요합니다.',
                )

            # exit code != 0: 실패 또는 UAC 취소
            return WindowsPrereqResult(
                ok=False,
                dry_run=False,
                target_prereq=request.target_prereq,
                status='failed',
                planned_steps=[],
                verification_commands=[],
                reboot_required=False,
                error='wsl_install_failed',
                message='WSL 설치 실행 실패. UAC를 취소했거나 명령 실패.',
            )

        except subprocess.TimeoutExpired:
            return WindowsPrereqResult(
                ok=False,
                dry_run=False,
                target_prereq=request.target_prereq,
                status='failed',
                planned_steps=[],
                verification_commands=[],
                reboot_required=False,
                error='wsl_install_timeout',
                message='WSL 설치 명령이 시간 초과되었습니다.',
            )

        except Exception as e:
            return WindowsPrereqResult(
                ok=False,
                dry_run=False,
                target_prereq=request.target_prereq,
                status='failed',
                planned_steps=[],
                verification_commands=[],
                reboot_required=False,
                error=f'wsl_install_error:{type(e).__name__}',
                message=f'WSL 설치 중 오류 발생: {type(e).__name__}',
            )

    def verify_windows_feature(self, target_prereq: str) -> dict:
        """Windows 기능 활성화 상태 검증.

        Args:
            target_prereq: 대상 ('wsl2', ...)

        Returns:
            검증 결과 dict
        """
        if target_prereq == 'wsl2':
            return self._verify_wsl_status()

        return {
            'target_prereq': target_prereq,
            'enabled': False,
            'error': f'unsupported_target_prereq',
        }

    def _verify_wsl_status(self) -> dict:
        """WSL 활성화 상태 검증.

        Returns:
            검증 결과 dict
        """
        try:
            result = subprocess.run(
                ['wsl', '--version'],
                timeout=10,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and 'WSL' in result.stdout:
                return {
                    'target_prereq': 'wsl2',
                    'enabled': True,
                    'version': result.stdout.strip(),
                    'error': None,
                }

            return {
                'target_prereq': 'wsl2',
                'enabled': False,
                'error': 'wsl_not_installed',
            }

        except FileNotFoundError:
            return {
                'target_prereq': 'wsl2',
                'enabled': False,
                'error': 'wsl_command_not_found',
            }

        except Exception as e:
            return {
                'target_prereq': 'wsl2',
                'enabled': False,
                'error': f'verify_error:{type(e).__name__}',
            }
