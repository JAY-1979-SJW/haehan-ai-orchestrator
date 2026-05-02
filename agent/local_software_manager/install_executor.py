"""프로그램 설치 실행 엔진 (dry_run 제어, 실행 전 검증, 1D: 카탈로그 기반)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List

from .. import errors as _err
from .models import SoftwareReport
from .report_builder import SoftwareReportBuilder
from .install_plan import InstallPlanBuilder
from .install_sources import INSTALL_SOURCES
from .detector import ProgramDetector
from .install_validator import InstallRequestValidator
from .download_provider import SoftwareDownloader
from .installer_verifier import InstallerFileVerifier
from .post_install_verifier import PostInstallVerifier
from .catalog import get_program


@dataclass(frozen=True)
class InstallExecutionRequest:
    """설치 실행 요청."""
    program_id: str
    approval_token: str
    dry_run: bool = True
    user_confirmed_install: bool = False
    user_accepted_license: bool = False  # 사용자가 명시적으로 약관 동의함
    local_installer_path: Optional[str] = None
    download_if_missing: bool = False
    user_confirmed_download: bool = False


@dataclass(frozen=True)
class InstallExecutionResult:
    """설치 실행 결과."""
    ok: bool
    dry_run: bool
    program_id: str
    program_name: str
    execution_enabled: bool
    requires_approval: bool
    requires_admin: bool
    requires_reboot: bool
    planned_steps: List[str]
    blocked_actions: List[str]
    current_status: str
    install_required: bool
    next_step: str
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return asdict(self)


class InstallExecutor:
    """설치 실행 엔진."""

    def execute(self, request: InstallExecutionRequest) -> InstallExecutionResult:
        """설치 실행 요청 처리.

        Args:
            request: InstallExecutionRequest

        Returns:
            InstallExecutionResult (dry_run 또는 실행 결과)
        """
        # 요청 검증
        validator = InstallRequestValidator()
        validation = validator.validate({
            'program_id': request.program_id,
            'approval_token': request.approval_token,
        })

        if not validation.ok:
            return InstallExecutionResult(
                ok=False,
                dry_run=request.dry_run,
                program_id=request.program_id,
                program_name='',
                execution_enabled=False,
                requires_approval=True,
                requires_admin=False,
                requires_reboot=False,
                planned_steps=[],
                blocked_actions=[],
                current_status='unknown',
                install_required=False,
                next_step='승인 토큰 확인 후 재시도',
                error=validation.error,
            )

        # 설치 계획 조회
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        # 대상 프로그램 찾기
        target_plan = None
        for plan in plan_report.plans:
            if plan.program_id == request.program_id:
                target_plan = plan
                break

        if not target_plan:
            return InstallExecutionResult(
                ok=False,
                dry_run=request.dry_run,
                program_id=request.program_id,
                program_name='',
                execution_enabled=False,
                requires_approval=True,
                requires_admin=False,
                requires_reboot=False,
                planned_steps=[],
                blocked_actions=[],
                current_status='unknown',
                install_required=False,
                next_step='프로그램을 찾을 수 없음',
                error=_err.INSTALL_NOT_REQUIRED,
            )

        # 이미 설치된 프로그램
        if not target_plan.install_required:
            return InstallExecutionResult(
                ok=True,
                dry_run=request.dry_run,
                program_id=target_plan.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=False,
                requires_admin=False,
                requires_reboot=False,
                planned_steps=[],
                blocked_actions=[],
                current_status='installed',
                install_required=False,
                next_step='이미 설치되어 있음',
            )

        # dry_run=true: 계획만 반환
        if request.dry_run:
            planned_steps = self._get_planned_steps(target_plan)
            return InstallExecutionResult(
                ok=True,
                dry_run=True,
                program_id=target_plan.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=True,
                requires_admin=target_plan.admin_required,
                requires_reboot=target_plan.reboot_may_be_required,
                planned_steps=planned_steps,
                blocked_actions=['download', 'install_execute', 'admin_elevation'],
                current_status='missing',
                install_required=True,
                next_step='dry_run 계획 검토 후 실제 실행 단계에서 진행',
            )

        # dry_run=false: 카탈로그 기반 통합 실행 (1D)
        program = get_program(request.program_id)
        if program and program.supports_auto_install and request.user_confirmed_install:
            return self._execute_install(request, target_plan, program)

        # dry_run=false: supports_auto_install=false는 차단
        return InstallExecutionResult(
            ok=False,
            dry_run=False,
            program_id=target_plan.program_id,
            program_name=target_plan.name,
            execution_enabled=False,
            requires_approval=True,
            requires_admin=target_plan.admin_required,
            requires_reboot=target_plan.reboot_may_be_required,
            planned_steps=[],
            blocked_actions=['download', 'install_execute', 'admin_elevation'],
            current_status='missing',
            install_required=True,
            next_step=f'{target_plan.name}은 자동 설치를 지원하지 않습니다.',
            error=_err.EXECUTION_NOT_ENABLED_YET,
        )

    def _get_planned_steps(self, plan) -> List[str]:
        """설치 계획 단계 생성."""
        steps = []

        # 공식 설치 페이지 열기
        if plan.official_url:
            steps.append(f"공식 설치 페이지 열기: {plan.official_url}")

        # 설치 방식별 단계
        if plan.install_method == 'official_installer':
            steps.append("사용자가 설치파일 다운로드")
            if plan.admin_required:
                steps.append("관리자 권한으로 설치파일 실행")
            else:
                steps.append("설치파일 실행")
            if plan.reboot_may_be_required:
                steps.append("필요시 시스템 재부팅")
        elif plan.install_method == 'manual_download':
            steps.append("공식 웹사이트에서 설치파일 수동 다운로드")
            if plan.admin_required:
                steps.append("관리자 권한으로 설치파일 실행")
            else:
                steps.append("설치파일 실행")
            if plan.reboot_may_be_required:
                steps.append("필요시 시스템 재부팅")

        # 라이선스 고지
        if plan.license_notice_required:
            steps.append("라이선스 약관 확인 및 동의")

        # 설치 후 검증
        steps.append(f"설치 후 {plan.program_id} --version 또는 경로 검증")

        return steps

    def verify_installation(self, program_id: str) -> dict:
        """설치 후 검증.

        Args:
            program_id: 프로그램 ID

        Returns:
            검증 결과 dict
        """
        program = get_program(program_id)
        if not program:
            return {
                'program_id': program_id,
                'installed': False,
                'version': 'unknown',
                'path': 'unknown',
            }

        detector = ProgramDetector()
        installed, version, path = detector.check_program(program, check_version=False)

        return {
            'program_id': program_id,
            'installed': installed,
            'version': version or 'unknown',
            'path': path or 'unknown',
        }

    def _execute_install(
        self,
        request: InstallExecutionRequest,
        target_plan,
        program,
    ) -> InstallExecutionResult:
        """통합 설치 실행 (1D: 카탈로그 기반).

        Args:
            request: 설치 요청
            target_plan: 설치 계획
            program: 프로그램 정의

        Returns:
            설치 결과
        """
        installer_path = request.local_installer_path

        # 현재 상태 확인
        detector = ProgramDetector()
        installed_before, _, _ = detector.check_program(program, check_version=False)

        if installed_before:
            return InstallExecutionResult(
                ok=True,
                dry_run=False,
                program_id=request.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=False,
                requires_admin=False,
                requires_reboot=False,
                planned_steps=[],
                blocked_actions=[],
                current_status='installed',
                install_required=False,
                next_step=f'{target_plan.name}은 이미 설치되어 있습니다.',
            )

        # 설치파일 경로 검증
        if not installer_path:
            return InstallExecutionResult(
                ok=False,
                dry_run=False,
                program_id=request.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=True,
                requires_admin=program.admin_required_for_install,
                requires_reboot=False,
                planned_steps=[],
                blocked_actions=['download'],
                current_status='missing',
                install_required=True,
                next_step=f'{target_plan.name} 설치파일이 필요합니다.',
                error='installer_path_required',
            )

        verifier = InstallerFileVerifier()
        valid, error_code = verifier.validate_installer_path(request.program_id, installer_path)
        if not valid:
            return InstallExecutionResult(
                ok=False,
                dry_run=False,
                program_id=request.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=True,
                requires_admin=program.admin_required_for_install,
                requires_reboot=False,
                planned_steps=[],
                blocked_actions=['install_execute'],
                current_status='missing',
                install_required=True,
                next_step='설치파일 검증 실패',
                error=error_code or 'installer_validation_failed',
            )

        # 설치 실행 (Start-Process -Verb RunAs)
        success, error = self._execute_installer_file(
            installer_path,
            program=program,
            user_accepted_license=request.user_accepted_license,
        )

        # 설치 후 상태 확인
        detector = ProgramDetector()
        installed_after, version, _ = detector.check_program(program, check_version=False)

        # 설치 후 검증
        post_verifier = PostInstallVerifier()
        verification = post_verifier.verify(request.program_id)

        # 설치 성공
        if installed_after:
            return InstallExecutionResult(
                ok=True,
                dry_run=False,
                program_id=request.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=False,
                requires_admin=False,
                requires_reboot=verification.reboot_may_be_required,
                planned_steps=[],
                blocked_actions=[],
                current_status='installed',
                install_required=False,
                next_step=verification.message,
            )

        # 설치 실패 (success=true이지만 설치 미확인 → 재부팅 필요 가능)
        if success:
            return InstallExecutionResult(
                ok=False,
                dry_run=False,
                program_id=request.program_id,
                program_name=target_plan.name,
                execution_enabled=False,
                requires_approval=False,
                requires_admin=False,
                requires_reboot=True,
                planned_steps=[],
                blocked_actions=[],
                current_status='missing',
                install_required=True,
                next_step=f'{target_plan.name} 설치 후 시스템 재부팅이 필요할 수 있습니다.',
                error='install_requires_reboot',
            )

        # 설치 실패 (error)
        return InstallExecutionResult(
            ok=False,
            dry_run=False,
            program_id=request.program_id,
            program_name=target_plan.name,
            execution_enabled=False,
            requires_approval=True,
            requires_admin=program.admin_required_for_install,
            requires_reboot=False,
            planned_steps=[],
            blocked_actions=[],
            current_status='missing',
            install_required=True,
            next_step=f'{target_plan.name} 설치 실패. 수동 설치를 권장합니다.',
            error=error or 'install_unknown_error',
        )

    def _execute_installer_file(
        self,
        installer_path: str,
        program=None,
        user_accepted_license: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """설치파일 실행 (Windows Start-Process -Verb RunAs).

        Args:
            installer_path: 설치파일 경로
            program: 프로그램 정의 (license_acceptance 플래그 확인용)
            user_accepted_license: 사용자가 약관에 동의했는지 여부

        Returns:
            (success, error_message)

        Note:
            UAC 팝업은 사용자가 직접 승인합니다.
            관리자 비밀번호 저장/전달 없음.
            --accept-license는 user_accepted_license=true일 때만 포함.
        """
        try:
            # ArgumentList 구성 (Docker: "install" + 조건부 "--accept-license")
            args = ['install']
            if (
                program
                and program.license_acceptance_supported
                and program.license_acceptance_flag
                and user_accepted_license
            ):
                args.append(program.license_acceptance_flag)

            args_str = ' '.join(args)
            cmd = f'Start-Process -FilePath "{installer_path}" -Verb RunAs -Wait -ArgumentList "{args_str}"'

            result = subprocess.run(
                [
                    'powershell',
                    '-Command',
                    cmd,
                ],
                timeout=600,
                capture_output=True,
            )
            return result.returncode == 0, None
        except subprocess.TimeoutExpired:
            return False, 'install_timeout'
        except Exception as e:
            return False, f'install_error:{type(e).__name__}'
