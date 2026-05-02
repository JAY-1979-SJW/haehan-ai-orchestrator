"""로컬 소프트웨어 관리자.

설치된 프로그램 상태 진단 (read-only).
"""
from .models import SoftwareProgram, SoftwareSummary, SoftwareReport
from .catalog import get_catalog, get_program
from .detector import ProgramDetector
from .report_builder import SoftwareReportBuilder

__all__ = [
    'SoftwareProgram',
    'SoftwareSummary',
    'SoftwareReport',
    'get_catalog',
    'get_program',
    'ProgramDetector',
    'SoftwareReportBuilder',
]
