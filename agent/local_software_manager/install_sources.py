"""프로그램 설치 정보 (메타데이터만, 실제 설치 금지)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InstallSource:
    """프로그램 설치 정보."""
    program_id: str
    name: str
    official_url: str
    method: str  # official_installer, manual_download, winget_manual
    admin_required: bool = False
    reboot_may_be_required: bool = False
    license_notice_required: bool = False
    recommended: bool = True


# 설치 정보 카탈로그 (메타데이터만, 실제 다운로드/설치 금지)
INSTALL_SOURCES = {
    'docker': InstallSource(
        program_id='docker',
        name='Docker Desktop',
        official_url='https://www.docker.com/products/docker-desktop/',
        method='official_installer',
        admin_required=True,
        reboot_may_be_required=True,
        license_notice_required=True,
        recommended=True,
    ),
    'git': InstallSource(
        program_id='git',
        name='Git',
        official_url='https://git-scm.com/download/win',
        method='official_installer',
        admin_required=False,
        reboot_may_be_required=False,
        license_notice_required=False,
        recommended=True,
    ),
    'python': InstallSource(
        program_id='python',
        name='Python',
        official_url='https://www.python.org/downloads/windows/',
        method='official_installer',
        admin_required=False,
        reboot_may_be_required=False,
        license_notice_required=False,
        recommended=True,
    ),
    'node': InstallSource(
        program_id='node',
        name='Node.js',
        official_url='https://nodejs.org/en/download/package-manager/',
        method='official_installer',
        admin_required=False,
        reboot_may_be_required=False,
        license_notice_required=False,
        recommended=True,
    ),
    'chrome': InstallSource(
        program_id='chrome',
        name='Google Chrome',
        official_url='https://www.google.com/chrome/downloads/',
        method='official_installer',
        admin_required=False,
        reboot_may_be_required=False,
        license_notice_required=False,
        recommended=True,
    ),
    'vscode': InstallSource(
        program_id='vscode',
        name='Visual Studio Code',
        official_url='https://code.visualstudio.com/download',
        method='official_installer',
        admin_required=False,
        reboot_may_be_required=False,
        license_notice_required=False,
        recommended=True,
    ),
    'hancom': InstallSource(
        program_id='hancom',
        name='Hancom Office',
        official_url='https://www.hancom.com/product/office/',
        method='manual_download',
        admin_required=True,
        reboot_may_be_required=True,
        license_notice_required=True,
        recommended=False,  # 선택적 설치
    ),
    'office': InstallSource(
        program_id='office',
        name='Microsoft Office / Excel',
        official_url='https://www.microsoft.com/microsoft-365/business/microsoft-365-apps-for-enterprise',
        method='manual_download',
        admin_required=True,
        reboot_may_be_required=True,
        license_notice_required=True,
        recommended=False,  # 선택적 설치
    ),
    'autocad': InstallSource(
        program_id='autocad',
        name='Autodesk AutoCAD',
        official_url='https://www.autodesk.com/products/autocad/overview',
        method='manual_download',
        admin_required=True,
        reboot_may_be_required=True,
        license_notice_required=True,
        recommended=False,  # 선택적 설치
    ),
}


def get_install_source(program_id: str) -> Optional[InstallSource]:
    """설치 정보 조회."""
    return INSTALL_SOURCES.get(program_id)
