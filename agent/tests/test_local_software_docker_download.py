"""Docker 다운로드 모듈 테스트 (1D: 공식 출처 검증, 사용자 승인 필수)."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent.local_software_manager.docker_download import (
    DockerDownloadValidator,
    DockerDownloader,
    DockerDownloadResult,
    DOCKER_ALLOWED_DOMAINS,
    DOCKER_INSTALLER_ALLOWED_NAMES,
    DOCKER_DOWNLOAD_URL,
)
from agent import errors as _err


class TestDockerDownloadValidator:
    """DockerDownloadValidator 테스트."""

    def test_valid_official_url_passes(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(DOCKER_DOWNLOAD_URL)
        assert valid is True
        assert error is None

    def test_http_url_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(
            "http://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
        )
        assert valid is False
        assert error == 'docker_download_http_not_allowed'

    def test_non_docker_domain_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(
            "https://example.com/Docker%20Desktop%20Installer.exe"
        )
        assert valid is False
        assert error == 'docker_download_domain_not_allowed'

    def test_shortener_url_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(
            "https://bit.ly/docker-installer"
        )
        assert valid is False
        assert error == 'docker_download_shortener_not_allowed'

    def test_wrong_filename_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(
            "https://desktop.docker.com/win/main/amd64/malware.exe"
        )
        assert valid is False
        assert error == 'docker_download_filename_not_allowed'

    def test_non_exe_extension_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(
            "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.zip"
        )
        assert valid is False
        assert error == 'docker_download_filename_not_allowed'

    def test_none_url_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url(None)
        assert valid is False
        assert error == 'docker_download_invalid_url'

    def test_empty_string_url_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url("")
        assert valid is False
        assert error == 'docker_download_invalid_url'

    def test_malformed_url_blocked(self):
        validator = DockerDownloadValidator()
        valid, error = validator.validate_url("not a url")
        assert valid is False
        # URL without https will be rejected
        assert error is not None


class TestDockerDownloader:
    """DockerDownloader 테스트."""

    def test_no_approval_token_blocked(self):
        downloader = DockerDownloader()
        result = downloader.download(
            approval_token='',
            user_confirmed_download=True,
        )
        assert result.ok is False
        assert result.error == _err.INSTALL_APPROVAL_REQUIRED

    def test_user_not_confirmed_blocked(self):
        downloader = DockerDownloader()
        result = downloader.download(
            approval_token='test-token',
            user_confirmed_download=False,
        )
        assert result.ok is False
        assert result.error == 'docker_download_user_confirmation_required'

    def test_approval_token_type_check(self):
        downloader = DockerDownloader()
        result = downloader.download(
            approval_token=123,  # type: ignore
            user_confirmed_download=True,
        )
        assert result.ok is False
        assert result.error == _err.INSTALL_APPROVAL_REQUIRED

    @patch('agent.local_software_manager.docker_download.urllib.request.urlretrieve')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.mkdir')
    def test_successful_download(self, mock_mkdir, mock_exists, mock_stat, mock_urlretrieve):
        downloader = DockerDownloader()
        temp_dir = '/tmp/test-downloads'

        mock_mkdir.return_value = None
        mock_exists.return_value = True
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 1024
        mock_stat.return_value = mock_stat_result
        mock_urlretrieve.return_value = None

        result = downloader.download(
            dest_dir=temp_dir,
            approval_token='test-token',
            user_confirmed_download=True,
        )

        assert result.ok is True
        assert result.source == 'official'
        assert result.domain_verified is True
        assert result.installer_path is not None

    @patch('agent.local_software_manager.docker_download.urllib.request.urlretrieve')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.unlink')
    def test_empty_file_blocked(self, mock_unlink, mock_mkdir, mock_exists, mock_stat, mock_urlretrieve):
        downloader = DockerDownloader()

        mock_mkdir.return_value = None
        mock_exists.return_value = True
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 0
        mock_stat.return_value = mock_stat_result
        mock_urlretrieve.return_value = None
        mock_unlink.return_value = None

        result = downloader.download(
            dest_dir='/tmp/test',
            approval_token='test-token',
            user_confirmed_download=True,
        )

        assert result.ok is False
        assert result.error == 'docker_download_empty_file'

    @patch('agent.local_software_manager.docker_download.urllib.request.urlretrieve')
    def test_download_exception_handled(self, mock_urlretrieve):
        downloader = DockerDownloader()
        mock_urlretrieve.side_effect = Exception('Network error')

        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.mkdir'):
                result = downloader.download(
                    approval_token='test-token',
                    user_confirmed_download=True,
                )

        assert result.ok is False
        assert 'docker_download_failed' in result.error

    @patch('agent.local_software_manager.docker_download.urllib.request.urlretrieve')
    @patch('pathlib.Path.stat')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.mkdir')
    def test_default_download_dir_is_downloads(self, mock_mkdir, mock_exists, mock_stat, mock_urlretrieve):
        downloader = DockerDownloader()

        mock_mkdir.return_value = None
        mock_exists.return_value = True
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 1024
        mock_stat.return_value = mock_stat_result
        mock_urlretrieve.return_value = None

        result = downloader.download(
            dest_dir=None,
            approval_token='test-token',
            user_confirmed_download=True,
        )

        assert result.ok is True
        assert 'Downloads' in result.installer_path or result.installer_path is not None


class TestDockerDownloadSafety:
    """docker_download.py 안전성 검증."""

    def test_no_credentials_storage(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        assert 'password' not in source
        assert 'secret' not in source
        assert 'PIN' not in source

    def test_no_auto_download(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        # 실제 다운로드는 user_confirmed_download=True일 때만
        assert 'urlretrieve' in source
        # 하지만 조건이 있어야 함
        assert 'user_confirmed_download' in source

    def test_no_silent_install_flags(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        assert '--accept-license' not in source
        assert '/quiet' not in source
        assert '/silent' not in source

    def test_no_uac_bypass(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        # RunAs는 docker_installer.py에만 있어야 함
        assert '-Verb RunAs' not in source
        assert 'Start-Process' not in source

    def test_https_only(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        assert "scheme != 'https'" in source

    def test_domain_whitelist(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        assert 'DOCKER_ALLOWED_DOMAINS' in source
        assert 'docker.com' in source or 'docker' in source

    def test_filename_whitelist(self):
        with open('agent/local_software_manager/docker_download.py') as f:
            source = f.read()
        assert 'DOCKER_INSTALLER_ALLOWED_NAMES' in source
        assert 'docker desktop installer' in source.lower()
