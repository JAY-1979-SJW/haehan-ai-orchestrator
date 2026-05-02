"""프로그램 설치 실행 엔진 (dry_run 제어, 실행 전 검증)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, List

from .. import errors as _err
from .models import SoftwareReport
from .report_builder import SoftwareReportBuilder
from .install_plan import InstallPlanBuilder
from .install_sources import INSTALL_SOURCES
from .detector import ProgramDetector
from .install_validator import InstallRequestValidator


@dataclass(frozen=True)
class InstallExecutionRequest:
    """설치 실행 요청."""
    program_id: str
    approval_token: str
    dry_run: bool = True


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

        # dry_run=false: 1C에서는 execution_not_enabled_yet 차단
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
            next_step='설치 실행은 1D 단계에서 프로그램별로 개별 활성화',
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
        detector = ProgramDetector()
        installed, version, path = detector.check_program(program_id)

        return {
            'program_id': program_id,
            'installed': installed,
            'version': version or 'unknown',
            'path': path or 'unknown',
        }
