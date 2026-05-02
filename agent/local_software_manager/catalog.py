"""로컬 소프트웨어 카탈로그.

설치 가능한 프로그램 목록 및 메타데이터.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Callable


@dataclass(frozen=True)
class ProgramDefinition:
    """프로그램 정의."""
    id: str
    name: str
    version_command: str  # 버전 확인 명령어
    common_paths: List[str]  # 일반 설치 경로
    description: str
    admin_required_for_install: bool = False
    reboot_may_be_required: bool = False


# 진단 대상 프로그램 카탈로그
PROGRAMS_CATALOG = {
    'docker': ProgramDefinition(
        id='docker',
        name='Docker Desktop',
        version_command='docker --version',
        common_paths=[
            'C:\\Program Files\\Docker\\Docker\\docker.exe',
            'C:\\Program Files (x86)\\Docker\\Docker\\docker.exe',
        ],
        description='컨테이너 플랫폼',
        admin_required_for_install=True,
        reboot_may_be_required=True,
    ),
    'git': ProgramDefinition(
        id='git',
        name='Git',
        version_command='git --version',
        common_paths=[
            'C:\\Program Files\\Git\\cmd\\git.exe',
            'C:\\Program Files (x86)\\Git\\cmd\\git.exe',
        ],
        description='분산 버전 관리 시스템',
    ),
    'python': ProgramDefinition(
        id='python',
        name='Python',
        version_command='python --version',
        common_paths=[
            'C:\\Users\\*\\AppData\\Local\\Programs\\Python\\Python*\\python.exe',
            'C:\\Program Files\\Python*\\python.exe',
            'C:\\Program Files (x86)\\Python*\\python.exe',
        ],
        description='프로그래밍 언어',
    ),
    'node': ProgramDefinition(
        id='node',
        name='Node.js',
        version_command='node --version',
        common_paths=[
            'C:\\Program Files\\nodejs\\node.exe',
            'C:\\Program Files (x86)\\nodejs\\node.exe',
        ],
        description='JavaScript 런타임',
    ),
    'chrome': ProgramDefinition(
        id='chrome',
        name='Google Chrome',
        version_command='',  # version 명령 없음, 경로만 확인
        common_paths=[
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        ],
        description='웹 브라우저',
    ),
    'vscode': ProgramDefinition(
        id='vscode',
        name='Visual Studio Code',
        version_command='code --version',
        common_paths=[
            'C:\\Program Files\\Microsoft VS Code\\bin\\code.cmd',
            'C:\\Program Files (x86)\\Microsoft VS Code\\bin\\code.cmd',
        ],
        description='코드 편집기',
    ),
    'hancom': ProgramDefinition(
        id='hancom',
        name='Hancom Office',
        version_command='',  # version 명령 없음, 경로만 확인
        common_paths=[
            'C:\\Program Files\\Hancom\\HOffice*\\Bin\\hwp.exe',
            'C:\\Program Files (x86)\\Hancom\\HOffice*\\Bin\\hwp.exe',
        ],
        description='한글 오피스 제품',
        admin_required_for_install=True,
    ),
    'office': ProgramDefinition(
        id='office',
        name='Microsoft Office / Excel',
        version_command='',  # version 명령 없음, registry만 확인
        common_paths=[
            'C:\\Program Files\\Microsoft Office\\root\\Office*\\EXCEL.EXE',
            'C:\\Program Files (x86)\\Microsoft Office\\root\\Office*\\EXCEL.EXE',
        ],
        description='마이크로소프트 오피스',
        admin_required_for_install=True,
        reboot_may_be_required=True,
    ),
    'autocad': ProgramDefinition(
        id='autocad',
        name='Autodesk AutoCAD',
        version_command='',  # version 명령 없음, 경로만 확인
        common_paths=[
            'C:\\Program Files\\Autodesk\\AutoCAD*\\acad.exe',
            'C:\\Program Files (x86)\\Autodesk\\AutoCAD*\\acad.exe',
        ],
        description='CAD 설계 소프트웨어',
        admin_required_for_install=True,
        reboot_may_be_required=True,
    ),
}


def get_catalog() -> dict[str, ProgramDefinition]:
    """카탈로그 반환."""
    return PROGRAMS_CATALOG


def get_program(program_id: str) -> Optional[ProgramDefinition]:
    """특정 프로그램 조회."""
    return PROGRAMS_CATALOG.get(program_id)
