"""카탈로그 기반 통합 다운로드/설치 파이프라인 테스트 (1D)."""
import pytest
from pathlib import Path
from agent.local_software_manager.catalog import get_program
from agent.local_software_manager.download_provider import SoftwareDownloader, DownloadValidator
from agent.local_software_manager.installer_verifier import InstallerFileVerifier
from agent.local_software_manager.post_install_verifier import PostInstallVerifier


class TestCatalogMetadata:
    """카탈로그 메타데이터 검증."""

    def test_docker_catalog(self):
        """Docker 카탈로그 확인."""
        program = get_program('docker')
        assert program is not None
        assert program.supports_auto_download is True
        assert program.supports_auto_install is True
        assert 'docker.com' in program.official_domains
        assert 'desktop.docker.com' in program.official_domains

    def test_git_catalog(self):
        """Git 카탈로그 확인."""
        program = get_program('git')
        assert program is not None
        assert program.supports_auto_download is True
        assert program.supports_auto_install is False

    def test_python_catalog(self):
        """Python 카탈로그 확인."""
        program = get_program('python')
        assert program is not None
        assert program.supports_auto_download is True
        assert program.supports_auto_install is False

    def test_hancom_catalog(self):
        """Hancom 카탈로그 확인."""
        program = get_program('hancom')
        assert program is not None
        assert program.supports_auto_download is False
        assert program.supports_auto_install is False

    def test_office_catalog(self):
        """Office 카탈로그 확인."""
        program = get_program('office')
        assert program is not None
        assert program.supports_auto_download is False
        assert program.supports_auto_install is False


class TestDownloadValidator:
    """다운로드 URL 검증."""

    def test_docker_official_domain_valid(self):
        """Docker 공식 도메인 검증."""
        validator = DownloadValidator()
        valid, error = validator.validate_url(
            'docker',
            'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
        )
        assert valid is True
        assert error is None

    def test_docker_http_not_allowed(self):
        """HTTP URL 차단."""
        validator = DownloadValidator()
        valid, error = validator.validate_url(
            'docker',
            'http://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
        )
        assert valid is False
        assert error == 'download_http_not_allowed'

    def test_docker_shortener_blocked(self):
        """단축 URL 차단."""
        validator = DownloadValidator()
        valid, error = validator.validate_url(
            'docker',
            'https://bit.ly/docker-installer'
        )
        assert valid is False
        assert error == 'download_shortener_not_allowed'

    def test_docker_wrong_domain(self):
        """공식 도메인 외 URL 차단."""
        validator = DownloadValidator()
        valid, error = validator.validate_url(
            'docker',
            'https://example.com/docker-installer.exe'
        )
        assert valid is False
        assert error == 'download_domain_not_allowed'

    def test_git_official_domain(self):
        """Git 공식 도메인 검증."""
        validator = DownloadValidator()
        valid, error = validator.validate_url(
            'git',
            'https://git-scm.com/download/win/Git-2.40.0-64-bit.exe'
        )
        assert valid is True

    def test_program_not_found(self):
        """프로그램 찾기 실패."""
        validator = DownloadValidator()
        valid, error = validator.validate_url(
            'invalid_program',
            'https://example.com/installer.exe'
        )
        assert valid is False


class TestInstallerVerifier:
    """설치파일 검증."""

    def test_docker_installer_valid_path(self, tmp_path):
        """Docker 설치파일 경로 검증."""
        # 테스트 파일 생성
        installer_file = tmp_path / 'Docker Desktop Installer.exe'
        installer_file.touch()

        verifier = InstallerFileVerifier()
        valid, error = verifier.validate_installer_path(
            'docker',
            str(installer_file)
        )
        assert valid is True

    def test_docker_installer_invalid_extension(self, tmp_path):
        """잘못된 확장자 차단."""
        installer_file = tmp_path / 'Docker Desktop Installer.msi'
        installer_file.touch()

        verifier = InstallerFileVerifier()
        valid, error = verifier.validate_installer_path(
            'docker',
            str(installer_file)
        )
        assert valid is False

    def test_docker_installer_file_not_found(self):
        """파일 없음."""
        verifier = InstallerFileVerifier()
        valid, error = verifier.validate_installer_path(
            'docker',
            '/nonexistent/Docker Desktop Installer.exe'
        )
        assert valid is False

    def test_git_installer_valid_path(self, tmp_path):
        """Git 설치파일 경로 검증."""
        installer_file = tmp_path / 'Git-2.40.0-64-bit.exe'
        installer_file.touch()

        verifier = InstallerFileVerifier()
        valid, error = verifier.validate_installer_path(
            'git',
            str(installer_file)
        )
        assert valid is True


class TestPostInstallVerifier:
    """설치 후 검증."""

    def test_docker_verify_commands(self):
        """Docker verify_commands 확인."""
        program = get_program('docker')
        assert len(program.verify_commands) > 0
        assert 'docker --version' in program.verify_commands

    def test_git_verify_commands(self):
        """Git verify_commands 확인."""
        program = get_program('git')
        assert len(program.verify_commands) > 0
        assert 'git --version' in program.verify_commands

    def test_hancom_no_auto_install(self):
        """Hancom 자동 설치 불가."""
        program = get_program('hancom')
        assert program.supports_auto_install is False

    def test_office_no_auto_install(self):
        """Office 자동 설치 불가."""
        program = get_program('office')
        assert program.supports_auto_install is False


class TestDownloadPolicyEnforcement:
    """다운로드 정책 강제."""

    def test_docker_auto_download_enabled(self):
        """Docker 자동 다운로드 활성화."""
        program = get_program('docker')
        assert program.supports_auto_download is True

    def test_git_auto_download_enabled(self):
        """Git 자동 다운로드 활성화."""
        program = get_program('git')
        assert program.supports_auto_download is True

    def test_python_auto_download_enabled(self):
        """Python 자동 다운로드 활성화."""
        program = get_program('python')
        assert program.supports_auto_download is True

    def test_hancom_auto_download_disabled(self):
        """Hancom 자동 다운로드 비활성화."""
        program = get_program('hancom')
        assert program.supports_auto_download is False

    def test_office_auto_download_disabled(self):
        """Office 자동 다운로드 비활성화."""
        program = get_program('office')
        assert program.supports_auto_download is False

    def test_autocad_auto_download_disabled(self):
        """AutoCAD 자동 다운로드 비활성화."""
        program = get_program('autocad')
        assert program.supports_auto_download is False


class TestInstallPolicyEnforcement:
    """설치 정책 강제."""

    def test_docker_auto_install_enabled(self):
        """Docker 자동 설치 활성화."""
        program = get_program('docker')
        assert program.supports_auto_install is True

    def test_git_auto_install_disabled(self):
        """Git 자동 설치 비활성화 (dry_run만)."""
        program = get_program('git')
        assert program.supports_auto_install is False

    def test_python_auto_install_disabled(self):
        """Python 자동 설치 비활성화 (dry_run만)."""
        program = get_program('python')
        assert program.supports_auto_install is False

    def test_hancom_auto_install_disabled(self):
        """Hancom 자동 설치 비활성화."""
        program = get_program('hancom')
        assert program.supports_auto_install is False

    def test_office_auto_install_disabled(self):
        """Office 자동 설치 비활성화."""
        program = get_program('office')
        assert program.supports_auto_install is False


class TestAdminRequirement:
    """관리자 권한 요구."""

    def test_docker_requires_admin(self):
        """Docker 관리자 권한 필요."""
        program = get_program('docker')
        assert program.admin_required_for_install is True

    def test_git_no_admin(self):
        """Git 관리자 권한 불필요."""
        program = get_program('git')
        assert program.admin_required_for_install is False

    def test_python_no_admin(self):
        """Python 관리자 권한 불필요."""
        program = get_program('python')
        assert program.admin_required_for_install is False

    def test_hancom_requires_admin(self):
        """Hancom 관리자 권한 필요."""
        program = get_program('hancom')
        assert program.admin_required_for_install is True

    def test_office_requires_admin(self):
        """Office 관리자 권한 필요."""
        program = get_program('office')
        assert program.admin_required_for_install is True
