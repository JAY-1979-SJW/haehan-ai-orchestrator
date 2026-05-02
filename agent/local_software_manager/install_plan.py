"""프로그램 설치 계획 생성기.

설치가 필요한 프로그램의 설치 계획만 생성 (실제 설치 금지).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional
from .models import SoftwareReport
from .install_sources import INSTALL_SOURCES


@dataclass(frozen=True)
class InstallPlan:
    """프로그램 설치 계획."""
    program_id: str
    name: str
    current_status: str  # installed, missing, unknown
    install_required: bool
    recommended: bool
    install_method: str  # official_installer, manual_download, already_installed, unsupported_manual_only
    official_url: Optional[str] = None
    admin_required: bool = False
    reboot_may_be_required: bool = False
    license_notice_required: bool = False
    user_approval_required: bool = False
    execution_enabled: bool = False  # 항상 False (계획만 생성)
    notes: List[str] = None

    def __post_init__(self):
        if self.notes is None:
            object.__setattr__(self, 'notes', [])


@dataclass(frozen=True)
class InstallPlanSummary:
    """설치 계획 요약."""
    total: int
    installed: int
    install_required: int
    admin_required: int
    reboot_may_be_required: int


@dataclass(frozen=True)
class InstallPlanReport:
    """설치 계획 리포트."""
    ok: bool
    summary: InstallPlanSummary
    plans: List[InstallPlan]
    execution_enabled: bool = False
    next_step: str = "사용자 승인 후 설치 실행 단계에서만 진행"

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            'ok': self.ok,
            'summary': asdict(self.summary),
            'plans': [asdict(p) for p in self.plans],
            'execution_enabled': self.execution_enabled,
            'next_step': self.next_step,
        }


class InstallPlanBuilder:
    """설치 계획 생성기."""

    def build_plan(self, status_report: SoftwareReport) -> InstallPlanReport:
        """진단 결과를 기반으로 설치 계획 생성.

        Args:
            status_report: SoftwareReportBuilder의 결과

        Returns:
            InstallPlanReport
        """
        plans = []
        installed_count = 0
        install_required_count = 0
        admin_required_count = 0
        reboot_may_be_required_count = 0

        for program in status_report.programs:
            if program.installed:
                # 이미 설치됨
                plan = InstallPlan(
                    program_id=program.id,
                    name=program.name,
                    current_status='installed',
                    install_required=False,
                    recommended=False,
                    install_method='already_installed',
                    execution_enabled=False,
                )
                installed_count += 1
            else:
                # 설치 필요
                source = INSTALL_SOURCES.get(program.id)
                if not source:
                    # 설치 정보 없음
                    plan = InstallPlan(
                        program_id=program.id,
                        name=program.name,
                        current_status='unknown',
                        install_required=True,
                        recommended=False,
                        install_method='unsupported_manual_only',
                        execution_enabled=False,
                        notes=['설치 정보를 찾을 수 없습니다. 공식 웹사이트에서 수동 설치를 권장합니다.'],
                    )
                else:
                    # 설치 정보 있음
                    plan = InstallPlan(
                        program_id=program.id,
                        name=program.name,
                        current_status='missing',
                        install_required=True,
                        recommended=source.recommended,
                        install_method=source.method,
                        official_url=source.official_url,
                        admin_required=source.admin_required,
                        reboot_may_be_required=source.reboot_may_be_required,
                        license_notice_required=source.license_notice_required,
                        user_approval_required=True,
                        execution_enabled=False,
                    )

                    install_required_count += 1

                    if source.admin_required:
                        admin_required_count += 1

                    if source.reboot_may_be_required:
                        reboot_may_be_required_count += 1

            plans.append(plan)

        # 요약
        summary = InstallPlanSummary(
            total=len(plans),
            installed=installed_count,
            install_required=install_required_count,
            admin_required=admin_required_count,
            reboot_may_be_required=reboot_may_be_required_count,
        )

        return InstallPlanReport(
            ok=True,
            summary=summary,
            plans=plans,
            execution_enabled=False,
            next_step='사용자 승인 후 설치 실행 단계에서만 진행',
        )
