"""로컬 소프트웨어 관리자.

설치된 프로그램 상태 진단 (read-only) 및 설치 계획 생성 (실행 금지).
"""
from .models import SoftwareProgram, SoftwareSummary, SoftwareReport
from .catalog import get_catalog, get_program
from .detector import ProgramDetector
from .report_builder import SoftwareReportBuilder
from .install_plan import InstallPlan, InstallPlanSummary, InstallPlanReport, InstallPlanBuilder
from .install_sources import InstallSource, INSTALL_SOURCES, get_install_source

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
]
