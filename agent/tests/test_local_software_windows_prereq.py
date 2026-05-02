"""Windows 선행조건 활성화 테스트."""
import pytest
from agent.local_software_manager.windows_feature_executor import (
    WindowsFeatureExecutor,
    WindowsPrereqRequest,
)


class TestWindowsPrereqValidation:
    """Windows 선행조건 요청 검증 테스트."""

    def test_approval_token_required(self):
        """approval_token 없으면 차단."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='wsl2',
            approval_token='',  # 토큰 없음
            user_confirmed_windows_feature_change=True,
            dry_run=False,
        )
        result = executor.execute(request)
        assert not result.ok
        assert result.error == 'approval_token_required'

    def test_user_confirmation_required(self):
        """user_confirmed_windows_feature_change=false면 차단."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='wsl2',
            approval_token='valid-token',
            user_confirmed_windows_feature_change=False,  # 확인 안 함
            dry_run=False,
        )
        result = executor.execute(request)
        assert not result.ok
        assert result.error == 'user_confirmation_required'

    def test_unsupported_target_prereq(self):
        """지원하지 않는 target_prereq는 차단."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='unsupported',
            approval_token='valid-token',
            user_confirmed_windows_feature_change=True,
            dry_run=False,
        )
        result = executor.execute(request)
        assert not result.ok
        assert result.error == 'unsupported_target_prereq'

    def test_wsl2_target_accepted(self):
        """wsl2는 유효한 대상."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='wsl2',
            approval_token='valid-token',
            user_confirmed_windows_feature_change=True,
            dry_run=True,  # dry_run으로 검증
        )
        result = executor.execute(request)
        assert result.ok is True  # 승인 조건 충족


class TestWindowsDryRun:
    """Windows 선행조건 dry_run 테스트."""

    def test_dry_run_true_returns_plan(self):
        """dry_run=true이면 실행 계획 반환."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='wsl2',
            approval_token='valid-token',
            user_confirmed_windows_feature_change=True,
            dry_run=True,
        )
        result = executor.execute(request)
        assert result.ok is True
        assert result.dry_run is True
        assert len(result.planned_steps) > 0
        assert len(result.verification_commands) > 0

    def test_plan_includes_uac_step(self):
        """계획에 UAC 단계 포함."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='wsl2',
            approval_token='valid-token',
            user_confirmed_windows_feature_change=True,
            dry_run=True,
        )
        result = executor.execute(request)
        plan_text = ' '.join(result.planned_steps)
        assert 'UAC' in plan_text or '관리자' in plan_text

    def test_plan_includes_reboot_warning(self):
        """계획에 재부팅 경고 포함."""
        executor = WindowsFeatureExecutor()
        request = WindowsPrereqRequest(
            target_prereq='wsl2',
            approval_token='valid-token',
            user_confirmed_windows_feature_change=True,
            dry_run=True,
        )
        result = executor.execute(request)
        plan_text = ' '.join(result.planned_steps)
        assert '재부팅' in plan_text


class TestWindowsSafety:
    """Windows 선행조건 안전성 테스트."""

    def test_no_auto_reboot(self):
        """자동 재부팅 금지."""
        import inspect
        from agent.local_software_manager.windows_feature_executor import WindowsFeatureExecutor

        source = inspect.getsource(WindowsFeatureExecutor)
        # Restart-Computer, shutdown, reboot 명령 금지
        forbidden = ['Restart-Computer', 'shutdown /r', 'reboot /', '&& restart']
        for cmd in forbidden:
            assert cmd not in source, f'자동 재부팅 명령 발견: {cmd}'

    def test_no_credential_storage(self):
        """관리자 credential 저장 금지."""
        import inspect
        from agent.local_software_manager.windows_feature_executor import WindowsFeatureExecutor

        source = inspect.getsource(WindowsFeatureExecutor)
        # credential 저장 금지
        forbidden_patterns = ['RunAsCredential', 'PSCredential']
        for pattern in forbidden_patterns:
            assert pattern not in source, f'Credential 저장 발견: {pattern}'

    def test_no_docker_install(self):
        """Docker 설치 명령 금지."""
        import inspect
        from agent.local_software_manager.windows_feature_executor import WindowsFeatureExecutor

        source = inspect.getsource(WindowsFeatureExecutor)
        # Docker 설치 명령 금지
        assert 'Docker Desktop Installer' not in source
        assert 'docker install' not in source.lower()

    def test_uses_start_process_runAs(self):
        """Start-Process -Verb RunAs 사용 (UAC)."""
        import inspect
        from agent.local_software_manager.windows_feature_executor import WindowsFeatureExecutor

        source = inspect.getsource(WindowsFeatureExecutor)
        assert 'Start-Process' in source
        assert 'Verb RunAs' in source

    def test_no_password_in_code(self):
        """코드에 비밀번호 저장 없음."""
        import inspect
        from agent.local_software_manager.windows_feature_executor import WindowsFeatureExecutor

        source = inspect.getsource(WindowsFeatureExecutor)
        # 정확한 비밀번호 저장 패턴만 확인
        assert 'save_password' not in source
        assert 'store_password' not in source

    def test_wsl_install_no_launch_flag(self):
        """wsl --install에 --no-launch 플래그 포함."""
        import inspect
        from agent.local_software_manager.windows_feature_executor import WindowsFeatureExecutor

        source = inspect.getsource(WindowsFeatureExecutor)
        # 명령이 --no-launch를 포함하는지 확인
        assert 'wsl --install --no-launch' in source or '--no-launch' in source


class TestWindowsVerification:
    """Windows 기능 검증 테스트."""

    def test_verify_method_exists(self):
        """verify_windows_feature 메서드 존재."""
        executor = WindowsFeatureExecutor()
        assert hasattr(executor, 'verify_windows_feature')

    def test_unsupported_target_verification(self):
        """지원하지 않는 대상 검증 실패."""
        executor = WindowsFeatureExecutor()
        result = executor.verify_windows_feature('unsupported')
        assert result['enabled'] is False
        assert 'unsupported' in result['error'].lower()
