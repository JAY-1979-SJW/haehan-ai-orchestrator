"""소프트웨어 설치 계획 테스트."""
import pytest
from agent.local_software_manager import SoftwareReportBuilder
from agent.local_software_manager.install_plan import InstallPlanBuilder
from agent.local_software_manager.install_sources import get_install_source, INSTALL_SOURCES


class TestInstallSources:
    """설치 정보 테스트."""

    def test_all_programs_have_install_source(self):
        """모든 프로그램이 설치 정보 포함."""
        assert len(INSTALL_SOURCES) == 9

    def test_install_source_fields(self):
        """설치 정보 필드."""
        for program_id, source in INSTALL_SOURCES.items():
            assert source.program_id == program_id
            assert source.name
            assert source.official_url
            assert source.method
            assert source.method in ['official_installer', 'manual_download', 'winget_manual']

    def test_get_install_source(self):
        """설치 정보 조회."""
        docker_source = get_install_source('docker')
        assert docker_source is not None
        assert docker_source.admin_required is True
        assert docker_source.reboot_may_be_required is True

        missing = get_install_source('nonexistent')
        assert missing is None


class TestInstallPlanBuilder:
    """설치 계획 생성기 테스트."""

    def test_build_plan_structure(self):
        """설치 계획 구조."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        assert plan_report.ok is True
        assert plan_report.execution_enabled is False
        assert plan_report.summary.total == 9
        assert plan_report.summary.installed >= 0
        assert plan_report.summary.install_required >= 0

    def test_plan_summary_consistency(self):
        """설치 계획 요약 일관성."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        # installed + install_required == total
        assert (
            plan_report.summary.installed + plan_report.summary.install_required
            == plan_report.summary.total
        )

    def test_execution_enabled_always_false(self):
        """execution_enabled는 항상 False."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        assert plan_report.execution_enabled is False

        for plan in plan_report.plans:
            assert plan.execution_enabled is False

    def test_installed_programs_status(self):
        """설치된 프로그램 상태."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        # 설치된 프로그램 확인
        for plan in plan_report.plans:
            if plan.current_status == 'installed':
                assert plan.install_required is False
                assert plan.install_method == 'already_installed'

    def test_missing_programs_require_installation(self):
        """미설치 프로그램은 설치 필요."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        # 미설치 프로그램 확인
        for plan in plan_report.plans:
            if plan.current_status == 'missing':
                assert plan.install_required is True
                assert plan.user_approval_required is True

    def test_docker_admin_requirement(self):
        """Docker는 관리자 권한 필요."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        docker_plan = next((p for p in plan_report.plans if p.program_id == 'docker'), None)
        assert docker_plan is not None

        if docker_plan.install_required:
            assert docker_plan.admin_required is True
            assert docker_plan.reboot_may_be_required is True

    def test_plan_to_dict(self):
        """설치 계획 딕셔너리 변환."""
        status_builder = SoftwareReportBuilder()
        status_report = status_builder.build_report()

        plan_builder = InstallPlanBuilder()
        plan_report = plan_builder.build_plan(status_report)

        plan_dict = plan_report.to_dict()

        assert 'ok' in plan_dict
        assert 'summary' in plan_dict
        assert 'plans' in plan_dict
        assert 'execution_enabled' in plan_dict
        assert 'next_step' in plan_dict

        assert isinstance(plan_dict['summary'], dict)
        assert isinstance(plan_dict['plans'], list)
        assert plan_dict['execution_enabled'] is False


class TestSafety:
    """안전성 테스트."""

    def test_no_install_commands(self):
        """설치 명령 없음."""
        import inspect
        from agent.local_software_manager.install_plan import InstallPlanBuilder

        source = inspect.getsource(InstallPlanBuilder)

        forbidden = ['winget install', 'choco install', 'msiexec', 'RunAs']
        for word in forbidden:
            assert word not in source

    def test_no_download_commands(self):
        """다운로드 명령 없음."""
        import inspect
        from agent.local_software_manager.install_plan import InstallPlanBuilder

        source = inspect.getsource(InstallPlanBuilder)

        forbidden = ['download', 'urlretrieve', 'requests.get', 'httpx.get']
        for word in forbidden:
            assert word not in source

    def test_no_file_operations(self):
        """파일 조작 없음."""
        import inspect
        from agent.local_software_manager.install_plan import InstallPlanBuilder

        source = inspect.getsource(InstallPlanBuilder)

        forbidden = ['unlink', 'remove', 'rmdir', 'rename']
        for word in forbidden:
            assert word not in source

    def test_no_credentials_storage(self):
        """비밀번호/PIN 저장 없음."""
        import inspect
        from agent.local_software_manager.install_plan import InstallPlanBuilder

        source = inspect.getsource(InstallPlanBuilder)

        assert 'password' not in source
        assert 'secret' not in source
