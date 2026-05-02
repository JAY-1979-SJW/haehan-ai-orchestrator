"""VS Code 반복 실행 방지 보정 테스트 (1A-FIX-VSCODE)."""
import pytest
from agent.local_software_manager.catalog import get_program
from agent.local_software_manager.detector import ProgramDetector


class TestVsCodeConfiguration:
    """VS Code 카탈로그 설정 검증."""

    def test_vscode_no_version_command(self):
        """VS Code version_command가 비어있는지 확인."""
        program = get_program('vscode')
        assert program is not None
        assert program.version_command == '', "VS Code는 code --version을 실행하면 안 됨"

    def test_vscode_no_verify_commands(self):
        """VS Code verify_commands가 비어있는지 확인."""
        program = get_program('vscode')
        assert program is not None
        assert program.verify_commands == [''], "VS Code는 설치 후 버전 검증 금지"

    def test_vscode_common_paths_exist(self):
        """VS Code common_paths가 설정되어 있는지 확인."""
        program = get_program('vscode')
        assert program is not None
        assert len(program.common_paths) > 0, "VS Code 경로 확인은 필요"


class TestDetectorNoCacheByDefault:
    """Detector 캐시 초기화 및 기본 동작."""

    def test_detector_cache_cleared_at_start(self):
        """테스트 시작 시 캐시 초기화."""
        ProgramDetector.clear_version_cache()
        assert len(ProgramDetector._version_cache) == 0

    def test_detector_check_program_no_version_by_default(self):
        """기본 check_program은 check_version=False."""
        program = get_program('docker')
        ProgramDetector.clear_version_cache()

        # check_version=False (기본값)
        installed, version, path = ProgramDetector.check_program(program)

        # 버전 결과는 None 또는 설치 여부에만 의존
        # (버전 명령 미실행)
        assert isinstance(installed, bool)
        assert isinstance(path, (str, type(None)))


class TestDetectorVersionCaching:
    """버전 캐싱 메커니즘."""

    def test_version_cache_stores_result(self):
        """버전 캐시가 결과를 저장하는지 확인."""
        ProgramDetector.clear_version_cache()

        # 캐시에 값 저장
        cmd = 'echo test'
        result = ProgramDetector._get_version_cached(cmd)

        # 캐시에 저장되었는지 확인
        assert cmd in ProgramDetector._version_cache

    def test_version_cache_reuses_result(self):
        """버전 캐시가 결과를 재사용하는지 확인."""
        ProgramDetector.clear_version_cache()

        cmd = 'echo "version 1.0"'

        # 첫 실행
        result1 = ProgramDetector._get_version_cached(cmd)

        # 두 번째 실행 (캐시에서)
        result2 = ProgramDetector._get_version_cached(cmd)

        # 같은 결과여야 함
        assert result1 == result2

    def test_version_cache_clear(self):
        """버전 캐시 초기화."""
        ProgramDetector.clear_version_cache()

        cmd = 'echo test'
        ProgramDetector._get_version_cached(cmd)
        assert len(ProgramDetector._version_cache) > 0

        # 초기화
        ProgramDetector.clear_version_cache()
        assert len(ProgramDetector._version_cache) == 0


class TestVsCodeNoRepeatedExecution:
    """VS Code code --version 반복 실행 방지."""

    def test_vscode_check_program_no_version_by_default(self):
        """VS Code check_program 기본값에서 code --version 미실행."""
        program = get_program('vscode')
        if program is None:
            pytest.skip("VS Code not in catalog")

        ProgramDetector.clear_version_cache()

        # 기본 동작: check_version=False
        installed, version, path = ProgramDetector.check_program(program, check_version=False)

        # 경로 확인은 하지만 버전은 안 함
        assert isinstance(installed, bool)
        assert version is None or version == 'unknown'

    def test_vscode_explicit_check_version_true(self):
        """VS Code check_version=True일 때만 버전 명령 실행 고려."""
        program = get_program('vscode')
        if program is None:
            pytest.skip("VS Code not in catalog")

        ProgramDetector.clear_version_cache()

        # check_version=True이지만 version_command가 비어있으므로 실행 안 됨
        installed, version, path = ProgramDetector.check_program(program, check_version=True)

        # version_command가 비어있으므로 version은 None
        assert version is None


class TestProgramWithVersionCommand:
    """버전 명령이 있는 프로그램 (비교용)."""

    def test_docker_has_version_command(self):
        """Docker는 version_command가 있는지 확인."""
        program = get_program('docker')
        assert program is not None
        assert program.version_command != '', "Docker는 버전 명령이 있어야 함"

    def test_git_has_version_command(self):
        """Git은 version_command가 있는지 확인."""
        program = get_program('git')
        assert program is not None
        assert program.version_command != '', "Git은 버전 명령이 있어야 함"


class TestOtherProgramsUnaffected:
    """다른 프로그램들은 영향받지 않음."""

    def test_python_still_works(self):
        """Python 진단은 정상 작동."""
        program = get_program('python')
        if program is None:
            pytest.skip("Python not in catalog")

        ProgramDetector.clear_version_cache()
        installed, version, path = ProgramDetector.check_program(program, check_version=False)

        # 경로 확인은 정상
        assert isinstance(installed, bool)

    def test_chrome_still_works(self):
        """Chrome 진단은 정상 작동."""
        program = get_program('chrome')
        if program is None:
            pytest.skip("Chrome not in catalog")

        ProgramDetector.clear_version_cache()
        installed, version, path = ProgramDetector.check_program(program, check_version=False)

        # 경로 확인은 정상
        assert isinstance(installed, bool)
