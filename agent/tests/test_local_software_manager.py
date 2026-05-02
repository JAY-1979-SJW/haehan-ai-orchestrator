"""로컬 소프트웨어 관리자 테스트."""
import pytest
from agent.local_software_manager import (
    SoftwareReportBuilder,
    get_catalog,
    ProgramDetector,
)


class TestCatalog:
    """카탈로그 테스트."""

    def test_catalog_has_nine_programs(self):
        """카탈로그에 9개 프로그램 정의."""
        catalog = get_catalog()
        assert len(catalog) == 9

    def test_all_programs_have_required_fields(self):
        """모든 프로그램이 필수 필드 포함."""
        catalog = get_catalog()

        for program_id, program_def in catalog.items():
            assert program_def.id
            assert program_def.name
            assert program_def.common_paths
            assert len(program_def.common_paths) > 0

    def test_expected_programs_present(self):
        """예상 프로그램 존재."""
        catalog = get_catalog()
        expected_ids = {
            'docker', 'git', 'python', 'node', 'chrome',
            'vscode', 'hancom', 'office', 'autocad'
        }
        assert set(catalog.keys()) == expected_ids


class TestDetector:
    """프로그램 감지기 테스트."""

    def test_check_program_returns_tuple(self):
        """check_program 반환값 구조."""
        catalog = get_catalog()
        docker_def = catalog['docker']

        installed, version, path = ProgramDetector.check_program(docker_def)

        assert isinstance(installed, bool)
        assert version is None or isinstance(version, str)
        assert path is None or isinstance(path, str)

    def test_missing_program_returns_false(self):
        """없는 프로그램은 False 반환."""
        catalog = get_catalog()
        docker_def = catalog['docker']

        # Docker가 없다고 가정 (실제 환경에서는 다를 수 있음)
        installed, version, path = ProgramDetector.check_program(docker_def)

        if not installed:
            assert version is None or isinstance(version, str)
            assert path is None


class TestReportBuilder:
    """리포트 생성기 테스트."""

    def test_build_report_structure(self):
        """리포트 구조."""
        builder = SoftwareReportBuilder()
        report = builder.build_report()

        assert report.ok is True
        assert report.summary.total == 9
        assert report.summary.installed >= 0
        assert report.summary.missing >= 0
        assert len(report.programs) == 9
        assert isinstance(report.recommendations, list)

    def test_report_summary_consistency(self):
        """리포트 요약 일관성."""
        builder = SoftwareReportBuilder()
        report = builder.build_report()

        # installed + missing == total
        assert report.summary.installed + report.summary.missing == report.summary.total

        # needs_setup == missing
        assert report.summary.needs_setup == report.summary.missing

    def test_all_programs_included(self):
        """모든 프로그램 포함."""
        builder = SoftwareReportBuilder()
        report = builder.build_report()

        program_ids = {p.id for p in report.programs}
        expected_ids = {
            'docker', 'git', 'python', 'node', 'chrome',
            'vscode', 'hancom', 'office', 'autocad'
        }

        assert program_ids == expected_ids

    def test_program_fields(self):
        """프로그램 필드."""
        builder = SoftwareReportBuilder()
        report = builder.build_report()

        for program in report.programs:
            assert program.id
            assert program.name
            assert isinstance(program.installed, bool)
            assert isinstance(program.admin_required_for_install, bool)
            assert isinstance(program.reboot_may_be_required, bool)
            assert isinstance(program.notes, list)

    def test_report_to_dict(self):
        """리포트 딕셔너리 변환."""
        builder = SoftwareReportBuilder()
        report = builder.build_report()

        report_dict = report.to_dict()

        assert 'ok' in report_dict
        assert 'summary' in report_dict
        assert 'programs' in report_dict
        assert 'recommendations' in report_dict

        assert isinstance(report_dict['summary'], dict)
        assert isinstance(report_dict['programs'], list)
        assert len(report_dict['programs']) == 9


class TestSafety:
    """안전성 테스트."""

    def test_no_install_commands_in_detector(self):
        """detector에 설치 명령 없음."""
        import inspect
        source = inspect.getsource(ProgramDetector)

        forbidden = ['winget install', 'choco install', 'msiexec', 'RunAs']
        for word in forbidden:
            assert word not in source

    def test_no_file_operations(self):
        """파일 조작 없음."""
        import inspect
        source = inspect.getsource(ProgramDetector)

        forbidden = ['unlink', 'remove', 'rmdir', 'rename']
        for word in forbidden:
            assert word not in source

    def test_no_credentials_storage(self):
        """비밀번호/PIN 저장 없음."""
        import inspect
        source = inspect.getsource(ProgramDetector)

        assert 'password' not in source
        assert 'secret' not in source
