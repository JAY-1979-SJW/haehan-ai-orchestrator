"""Docker Desktop 전용 설치 테스트 (1D)."""
import pytest
from agent.local_software_manager import (
    DockerInstaller,
    DockerInstallerValidator,
    InstallExecutor,
    InstallExecutionRequest,
)


class TestDockerInstallerValidator:
    """Docker 설치파일 검증 테스트."""

    def test_path_none_blocked(self):
        """경로 None이면 차단."""
        validator = DockerInstallerValidator()
        success, error = validator.validate_path(None)
        assert not success
        assert error is not None

    def test_invalid_extension_blocked(self):
        """확장자 .exe가 아니면 차단."""
        validator = DockerInstallerValidator()
        success, error = validator.validate_path('setup.msi')
        assert not success
        assert error == 'docker_installer_invalid_extension'

    def test_unknown_filename_blocked(self):
        """파일명이 allowlist에 없으면 차단."""
        validator = DockerInstallerValidator()
        success, error = validator.validate_path('unknown_installer.exe')
        assert not success
        assert error == 'docker_installer_name_not_allowed'

    def test_valid_name_passes(self):
        """파일명이 allowlist에 있으면 통과 (파일 없으면 FILE_NOT_FOUND)."""
        validator = DockerInstallerValidator()
        success, error = validator.validate_path('Docker Desktop Installer.exe')
        # 파일이 없으므로 FILE_NOT_FOUND 에러 예상
        assert not success
        assert error == 'file_not_found'


class TestDockerInstaller:
    """Docker 설치 엔진 테스트."""

    def test_non_docker_program_blocked(self):
        """non-docker program은 실제 설치 실행 차단."""
        executor = InstallExecutor()
        request = InstallExecutionRequest(
            program_id='office',  # Docker가 아님 (office는 미설치)
            approval_token='valid-token',
            dry_run=False,
            user_confirmed_install=True,
        )
        result = executor.execute(request)
        # Docker 외 프로그램은 execution_not_enabled_yet으로 차단
        # office가 미설치 상태라면 실행 차단
        assert result.error == 'execution_not_enabled_yet'

    def test_no_approval_token_blocked(self):
        """approval_token 없으면 차단."""
        installer = DockerInstaller()
        result = installer.run_install(
            installer_path=None,
            approval_token='',
            user_confirmed_install=True,
        )
        assert result.status == 'install_failed'
        assert result.error is not None

    def test_dry_run_true_no_execute(self):
        """dry_run=true이면 실행 안 함."""
        executor = InstallExecutor()
        request = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
            dry_run=True,  # dry_run=true
            user_confirmed_install=True,
        )
        result = executor.execute(request)
        # dry_run=true 모드이므로 planned_steps 반환
        assert result.ok is True
        assert result.dry_run is True
        assert len(result.planned_steps) > 0

    def test_user_not_confirmed_blocked(self):
        """사용자 확인 없으면 차단."""
        installer = DockerInstaller()
        result = installer.run_install(
            installer_path=None,
            approval_token='valid-token',
            user_confirmed_install=False,  # 확인 안 함
        )
        assert result.status == 'install_failed'
        assert 'confirmation' in result.error.lower()

    def test_no_installer_returns_download_required(self):
        """설치파일 없으면 download_required 반환."""
        installer = DockerInstaller()
        result = installer.run_install(
            installer_path=None,  # 파일 없음
            approval_token='valid-token',
            user_confirmed_install=True,
        )
        assert result.status == 'download_required'
        assert result.official_url == 'https://www.docker.com/products/docker-desktop/'


class TestDockerSafety:
    """Docker 설치 안전성 테스트."""

    def test_no_credentials_storage(self):
        """비밀번호/PIN 저장 없음."""
        import inspect
        from agent.local_software_manager.docker_installer import DockerInstaller

        source = inspect.getsource(DockerInstaller)

        assert 'password' not in source
        assert 'secret' not in source.lower()

    def test_no_auto_download(self):
        """자동 다운로드 없음."""
        import inspect
        from agent.local_software_manager.docker_installer import DockerInstaller

        source = inspect.getsource(DockerInstaller)

        forbidden = ['urlretrieve', 'requests.get', 'httpx.get']
        for word in forbidden:
            assert word not in source

    def test_runAs_in_install_executor(self):
        """Start-Process -Verb RunAs는 공통 install_executor에 있음 (1D: 통합 설치)."""
        import inspect
        from agent.local_software_manager.docker_installer import DockerInstaller
        from agent.local_software_manager.install_executor import InstallExecutor

        docker_source = inspect.getsource(DockerInstaller)
        executor_source = inspect.getsource(InstallExecutor)

        # docker_installer에는 Start-Process -Verb RunAs가 있음
        assert 'Start-Process' in docker_source
        assert 'Verb RunAs' in docker_source

        # 1D: install_executor도 공통 설치 엔진이므로 Start-Process -Verb RunAs가 있음
        assert 'Start-Process' in executor_source
        assert 'Verb RunAs' in executor_source

    def test_docker_download_no_runAs(self):
        """docker_download.py에는 RunAs가 없음."""
        import inspect
        from agent.local_software_manager.docker_download import DockerDownloader

        source = inspect.getsource(DockerDownloader)

        assert 'Start-Process' not in source
        assert 'Verb RunAs' not in source
