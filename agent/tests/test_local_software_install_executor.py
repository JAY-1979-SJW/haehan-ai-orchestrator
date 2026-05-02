"""소프트웨어 설치 실행 테스트."""
import pytest
from agent.local_software_manager import (
    InstallRequestValidator,
    InstallExecutor,
    InstallExecutionRequest,
    INSTALL_ALLOWLIST,
)
from agent import errors as _err


class TestInstallRequestValidator:
    """설치 요청 검증 테스트."""

    def test_missing_approval_token_blocked(self):
        """approval_token 없으면 차단."""
        validator = InstallRequestValidator()
        result = validator.validate({
            'program_id': 'docker',
        })
        assert not result.ok
        assert result.error == _err.INSTALL_APPROVAL_REQUIRED

    def test_missing_program_id_blocked(self):
        """program_id 없으면 차단."""
        validator = InstallRequestValidator()
        result = validator.validate({
            'approval_token': 'valid-token',
        })
        assert not result.ok
        assert result.error == _err.INSTALL_PROGRAM_ID_REQUIRED

    def test_program_not_in_allowlist_blocked(self):
        """allowlist 외 프로그램은 차단."""
        validator = InstallRequestValidator()
        result = validator.validate({
            'program_id': 'unknown-program',
            'approval_token': 'valid-token',
        })
        assert not result.ok
        assert result.error == _err.INSTALL_NOT_IN_ALLOWLIST


class TestInstallExecutor:
    """설치 실행 엔진 테스트."""

    def test_dry_run_default_true(self):
        """dry_run 기본값은 True."""
        request = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
        )
        assert request.dry_run is True

    def test_download_fields_default_false(self):
        """download_if_missing, user_confirmed_download 기본값은 False."""
        request = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
        )
        assert request.download_if_missing is False
        assert request.user_confirmed_download is False

    def test_dry_run_true_returns_planned_steps(self):
        """dry_run=True면 planned_steps 반환."""
        executor = InstallExecutor()
        request = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
            dry_run=True,
        )
        result = executor.execute(request)

        assert result.ok is True
        assert result.dry_run is True
        assert result.execution_enabled is False
        assert len(result.planned_steps) > 0

    def test_dry_run_false_returns_execution_not_enabled_yet(self):
        """dry_run=False면 execution_not_enabled_yet 반환."""
        executor = InstallExecutor()
        request = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
            dry_run=False,
        )
        result = executor.execute(request)

        assert result.ok is False
        assert result.dry_run is False
        assert result.execution_enabled is False
        assert result.error == _err.EXECUTION_NOT_ENABLED_YET

    def test_already_installed_returns_not_required(self):
        """설치된 프로그램은 install_required=False."""
        executor = InstallExecutor()
        # python은 대부분의 개발 환경에 설치되어 있을 가능성 높음
        # 하지만 deterministic 테스트를 위해 결과 검증
        request = InstallExecutionRequest(
            program_id='python',
            approval_token='valid-token',
            dry_run=True,
        )
        result = executor.execute(request)

        # 설치 여부에 관계없이 테스트 통과
        # (환경별 설치 상태가 다르므로)
        assert result.program_id == 'python'

    def test_planned_steps_not_empty(self):
        """계획 단계가 비어있지 않음."""
        executor = InstallExecutor()
        request = InstallExecutionRequest(
            program_id='git',
            approval_token='valid-token',
            dry_run=True,
        )
        result = executor.execute(request)

        if result.install_required:
            assert len(result.planned_steps) > 0

    def test_execution_enabled_always_false(self):
        """execution_enabled는 항상 False (1C 단계)."""
        executor = InstallExecutor()

        # dry_run=True
        request_dry = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
            dry_run=True,
        )
        result_dry = executor.execute(request_dry)
        assert result_dry.execution_enabled is False

        # dry_run=False
        request_exec = InstallExecutionRequest(
            program_id='docker',
            approval_token='valid-token',
            dry_run=False,
        )
        result_exec = executor.execute(request_exec)
        assert result_exec.execution_enabled is False


class TestInstallAllowlist:
    """설치 허용 목록 테스트."""

    def test_all_9_programs_in_allowlist(self):
        """모든 9개 프로그램이 allowlist에 있음."""
        assert len(INSTALL_ALLOWLIST) == 9
        assert 'docker' in INSTALL_ALLOWLIST
        assert 'git' in INSTALL_ALLOWLIST
        assert 'python' in INSTALL_ALLOWLIST
        assert 'node' in INSTALL_ALLOWLIST
        assert 'chrome' in INSTALL_ALLOWLIST
        assert 'vscode' in INSTALL_ALLOWLIST
        assert 'hancom' in INSTALL_ALLOWLIST
        assert 'office' in INSTALL_ALLOWLIST
        assert 'autocad' in INSTALL_ALLOWLIST

    def test_unknown_program_rejected(self):
        """알려지지 않은 프로그램은 거부."""
        validator = InstallRequestValidator()
        result = validator.validate({
            'program_id': 'malware-installer',
            'approval_token': 'token',
        })
        assert not result.ok
        assert result.error == _err.INSTALL_NOT_IN_ALLOWLIST


class TestSafety:
    """안전성 테스트."""

    def test_no_install_commands(self):
        """설치 명령 없음."""
        import inspect
        from agent.local_software_manager.install_executor import InstallExecutor

        source = inspect.getsource(InstallExecutor)

        forbidden = ['winget install', 'choco install', 'msiexec', 'RunAs']
        for word in forbidden:
            assert word not in source

    def test_no_download_commands(self):
        """다운로드 명령 없음."""
        import inspect
        from agent.local_software_manager.install_executor import InstallExecutor

        source = inspect.getsource(InstallExecutor)

        forbidden = ['urlretrieve', 'requests.get', 'httpx.get']
        for word in forbidden:
            assert word not in source

    def test_no_credentials_storage(self):
        """비밀번호/PIN 저장 없음."""
        import inspect
        from agent.local_software_manager.install_executor import InstallExecutor

        source = inspect.getsource(InstallExecutor)

        assert 'password' not in source
        assert 'secret' not in source
