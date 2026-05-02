"""로컬 소프트웨어 관리자.

설치된 프로그램 상태 진단 (read-only), 설치 계획 생성 (실행 금지),
사용자 승인형 설치 실행 프레임워크 (dry_run 제어).
"""
from .models import SoftwareProgram, SoftwareSummary, SoftwareReport
from .catalog import get_catalog, get_program
from .detector import ProgramDetector
from .report_builder import SoftwareReportBuilder
from .install_plan import InstallPlan, InstallPlanSummary, InstallPlanReport, InstallPlanBuilder
from .install_sources import InstallSource, INSTALL_SOURCES, get_install_source
from .install_validator import InstallRequestValidator, ValidationResult, INSTALL_ALLOWLIST
from .install_executor import (
    InstallExecutor,
    InstallExecutionRequest,
    InstallExecutionResult,
)
from .docker_installer import (
    DockerInstaller,
    DockerInstallResult,
    DockerInstallerValidator,
)

__all__ = [
    'SoftwareProgram',
    'SoftwareSummary',
    'SoftwareReport',
    'get_catalog',
    'get_program',
    'ProgramDetector',
    'SoftwareReportBuilder',
    'InstallPlan',
    'InstallPlanSummary',
    'InstallPlanReport',
    'InstallPlanBuilder',
    'InstallSource',
    'INSTALL_SOURCES',
    'get_install_source',
    'InstallRequestValidator',
    'ValidationResult',
    'INSTALL_ALLOWLIST',
    'InstallExecutor',
    'InstallExecutionRequest',
    'InstallExecutionResult',
    'DockerInstaller',
    'DockerInstallResult',
    'DockerInstallerValidator',
]
