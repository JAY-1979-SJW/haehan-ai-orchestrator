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
    official_url: str = ''
    official_domains: frozenset = frozenset()  # 공식 다운로드 도메인
    installer_type: str = 'exe'  # 'exe', 'msi', 'zip' 등
    expected_filename_patterns: frozenset = frozenset()  # 파일명 패턴 (lowercase)
    license_notice_required: bool = False
    supports_auto_download: bool = False  # 자동 다운로드 지원 여부
    supports_auto_install: bool = False  # 자동 설치 실행 지원 여부
    verify_commands: List[str] = None  # 설치 후 검증 명령어


# 진단 대상 프로그램 카탈로그 (1D: 카탈로그 기반 통합 다운로드/설치)
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
        official_url='https://www.docker.com/products/docker-desktop/',
        official_domains=frozenset({'docker.com', 'desktop.docker.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset({'docker desktop installer.exe', 'dockerdesktopinstaller.exe'}),
        license_notice_required=True,
        supports_auto_download=True,
        supports_auto_install=True,
        verify_commands=['docker --version', 'docker compose version'],
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
        official_url='https://git-scm.com/download/win',
        official_domains=frozenset({'git-scm.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset({'git-*.exe', 'git*.exe'}),
        license_notice_required=False,
        supports_auto_download=True,
        supports_auto_install=False,
        verify_commands=['git --version'],
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
        official_url='https://www.python.org/downloads/windows/',
        official_domains=frozenset({'python.org', 'www.python.org'}),
        installer_type='exe',
        expected_filename_patterns=frozenset({'python-*.exe', 'python*.exe'}),
        license_notice_required=False,
        supports_auto_download=True,
        supports_auto_install=False,
        verify_commands=['python --version'],
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
        official_url='https://nodejs.org/en/download/',
        official_domains=frozenset({'nodejs.org', 'www.nodejs.org'}),
        installer_type='exe',
        expected_filename_patterns=frozenset({'node-*.exe', 'node*.exe'}),
        license_notice_required=False,
        supports_auto_download=True,
        supports_auto_install=False,
        verify_commands=['node --version', 'npm --version'],
    ),
    'chrome': ProgramDefinition(
        id='chrome',
        name='Google Chrome',
        version_command='',
        common_paths=[
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        ],
        description='웹 브라우저',
        official_url='https://www.google.com/chrome/downloads/',
        official_domains=frozenset({'google.com', 'www.google.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset({'chromeset*.exe', 'chrome*.exe'}),
        license_notice_required=False,
        supports_auto_download=True,
        supports_auto_install=False,
        verify_commands=[''],  # 경로만 확인
    ),
    'vscode': ProgramDefinition(
        id='vscode',
        name='Visual Studio Code',
        version_command='',  # read-only: 경로 확인만, code --version은 프로세스 깨울 수 있음
        common_paths=[
            'C:\\Program Files\\Microsoft VS Code\\bin\\code.cmd',
            'C:\\Program Files (x86)\\Microsoft VS Code\\bin\\code.cmd',
        ],
        description='코드 편집기',
        official_url='https://code.visualstudio.com/download',
        official_domains=frozenset({'visualstudio.com', 'code.visualstudio.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset({'vscode*.exe', 'codesetup*.exe'}),
        license_notice_required=False,
        supports_auto_download=True,
        supports_auto_install=False,
        verify_commands=[''],  # read-only 진단만, version 명령 없음
    ),
    'hancom': ProgramDefinition(
        id='hancom',
        name='Hancom Office',
        version_command='',
        common_paths=[
            'C:\\Program Files\\Hancom\\HOffice*\\Bin\\hwp.exe',
            'C:\\Program Files (x86)\\Hancom\\HOffice*\\Bin\\hwp.exe',
        ],
        description='한글 오피스 제품',
        admin_required_for_install=True,
        official_url='https://www.hancom.com/product/office/',
        official_domains=frozenset({'hancom.com', 'www.hancom.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset(),
        license_notice_required=True,
        supports_auto_download=False,
        supports_auto_install=False,
        verify_commands=[''],
    ),
    'office': ProgramDefinition(
        id='office',
        name='Microsoft Office / Excel',
        version_command='',
        common_paths=[
            'C:\\Program Files\\Microsoft Office\\root\\Office*\\EXCEL.EXE',
            'C:\\Program Files (x86)\\Microsoft Office\\root\\Office*\\EXCEL.EXE',
        ],
        description='마이크로소프트 오피스',
        admin_required_for_install=True,
        reboot_may_be_required=True,
        official_url='https://www.microsoft.com/microsoft-365/business/microsoft-365-apps-for-enterprise',
        official_domains=frozenset({'microsoft.com', 'www.microsoft.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset(),
        license_notice_required=True,
        supports_auto_download=False,
        supports_auto_install=False,
        verify_commands=[''],
    ),
    'autocad': ProgramDefinition(
        id='autocad',
        name='Autodesk AutoCAD',
        version_command='',
        common_paths=[
            'C:\\Program Files\\Autodesk\\AutoCAD*\\acad.exe',
            'C:\\Program Files (x86)\\Autodesk\\AutoCAD*\\acad.exe',
        ],
        description='CAD 설계 소프트웨어',
        admin_required_for_install=True,
        reboot_may_be_required=True,
        official_url='https://www.autodesk.com/products/autocad/overview',
        official_domains=frozenset({'autodesk.com', 'www.autodesk.com'}),
        installer_type='exe',
        expected_filename_patterns=frozenset(),
        license_notice_required=True,
        supports_auto_download=False,
        supports_auto_install=False,
        verify_commands=[''],
    ),
}


def get_catalog() -> dict[str, ProgramDefinition]:
    """카탈로그 반환."""
    return PROGRAMS_CATALOG


def get_program(program_id: str) -> Optional[ProgramDefinition]:
    """특정 프로그램 조회."""
    return PROGRAMS_CATALOG.get(program_id)
