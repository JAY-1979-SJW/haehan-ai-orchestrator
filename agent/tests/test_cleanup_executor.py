"""cleanup_executor.py 테스트."""

import pytest
from pathlib import Path

from agent.local_inventory.file_map.cleanup_executor import (
    validate_approval,
    execute_moves,
)
from agent.local_inventory.file_map.cleanup_preflight import (
    run_preflight,
    PreflightItem,
    PreflightReport,
)


class TestValidateApproval:
    """validate_approval 테스트."""

    def create_sample_preflight(self):
        """샘플 preflight report 생성."""
        return PreflightReport(
            preflight_id="test-preflight",
            total=1,
            ok_count=1,
            conflict_count=0,
            skipped_count=0,
            blocked_count=0,
            items=[
                PreflightItem(
                    operation_id="op-001",
                    source_path="C:\\source\\file.txt",
                    target_path="C:\\target\\file.txt",
                    category="documents",
                    status="ok",
                    reason="",
                )
            ],
        )

    def test_valid_approval(self):
        """유효한 승인."""
        preflight = self.create_sample_preflight()
        try:
            validate_approval(
                "user-approved-cleanup-abc123",
                True,
                preflight,
            )
        except ValueError:
            pytest.fail("Valid approval should not raise")

    def test_missing_token(self):
        """토큰 없음."""
        preflight = self.create_sample_preflight()
        with pytest.raises(ValueError, match="승인 토큰"):
            validate_approval("", True, preflight)

    def test_invalid_token_format(self):
        """토큰 형식 오류."""
        preflight = self.create_sample_preflight()
        with pytest.raises(ValueError, match="승인 토큰 형식"):
            validate_approval("invalid-token", True, preflight)

    def test_user_not_confirmed(self):
        """사용자 미확인."""
        preflight = self.create_sample_preflight()
        with pytest.raises(ValueError, match="사용자 최종 확인"):
            validate_approval("user-approved-cleanup-abc123", False, preflight)

    def test_no_ok_items(self):
        """승인 가능 항목 없음."""
        empty_preflight = PreflightReport(
            preflight_id="empty",
            total=0,
            ok_count=0,
            conflict_count=0,
            skipped_count=0,
            blocked_count=0,
            items=[],
        )
        with pytest.raises(ValueError, match="승인 가능한 항목"):
            validate_approval(
                "user-approved-cleanup-abc123",
                True,
                empty_preflight,
            )

    def test_has_conflicts(self):
        """충돌 항목 있음."""
        conflict_preflight = PreflightReport(
            preflight_id="conflict",
            total=2,
            ok_count=1,
            conflict_count=1,
            skipped_count=0,
            blocked_count=0,
            items=[
                PreflightItem(
                    operation_id="op-ok",
                    source_path="C:\\source\\file1.txt",
                    target_path="C:\\target\\file1.txt",
                    category="documents",
                    status="ok",
                    reason="",
                )
            ],
        )
        with pytest.raises(ValueError, match="충돌"):
            validate_approval(
                "user-approved-cleanup-abc123",
                True,
                conflict_preflight,
            )

    def test_has_blocked(self):
        """제외 항목 있음."""
        blocked_preflight = PreflightReport(
            preflight_id="blocked",
            total=2,
            ok_count=1,
            conflict_count=0,
            skipped_count=0,
            blocked_count=1,
            items=[
                PreflightItem(
                    operation_id="op-ok",
                    source_path="C:\\source\\file1.txt",
                    target_path="C:\\target\\file1.txt",
                    category="documents",
                    status="ok",
                    reason="",
                )
            ],
        )
        with pytest.raises(ValueError, match="제외"):
            validate_approval(
                "user-approved-cleanup-abc123",
                True,
                blocked_preflight,
            )


class TestExecuteMoves:
    """execute_moves 테스트."""

    def create_sample_preflight(self, tmp_path):
        """샘플 preflight report with real files."""
        source = tmp_path / "document.txt"
        source.write_text("content")

        target = tmp_path / "target" / "document.txt"
        target.parent.mkdir(exist_ok=True)

        return PreflightReport(
            preflight_id="test-preflight",
            total=1,
            ok_count=1,
            conflict_count=0,
            skipped_count=0,
            blocked_count=0,
            items=[
                PreflightItem(
                    operation_id="op-001",
                    source_path=str(source),
                    target_path=str(target),
                    category="documents",
                    status="ok",
                    reason="",
                )
            ],
        )

    def test_dry_run_no_actual_move(self, tmp_path):
        """dry_run 모드에서는 실제 이동 안 함."""
        preflight = self.create_sample_preflight(tmp_path)
        source_file = Path(preflight.items[0].source_path)

        result = execute_moves(
            preflight,
            "pkg-001",
            "user-approved-cleanup-abc123",
            True,
            dry_run=True,
        )

        assert result.success_count == 1
        assert source_file.exists()  # 원본 파일 여전히 존재

    def test_actual_move_execution(self, tmp_path):
        """실제 파일 이동 (dry_run=False)."""
        preflight = self.create_sample_preflight(tmp_path)
        source_path = Path(preflight.items[0].source_path)
        target_path = Path(preflight.items[0].target_path)

        result = execute_moves(
            preflight,
            "pkg-001",
            "user-approved-cleanup-abc123",
            True,
            dry_run=False,
        )

        assert result.success_count == 1
        assert not source_path.exists()  # 원본 파일 삭제됨
        assert target_path.exists()  # 대상 파일 생성됨

    def test_invalid_approval_raises(self, tmp_path):
        """유효하지 않은 승인."""
        preflight = self.create_sample_preflight(tmp_path)

        with pytest.raises(ValueError):
            execute_moves(
                preflight,
                "pkg-001",
                "invalid-token",
                True,
                dry_run=True,
            )

    def test_missing_source_skipped(self, tmp_path):
        """소스 파일 없으면 스킵."""
        missing_source = tmp_path / "missing.txt"
        target = tmp_path / "target" / "missing.txt"
        target.parent.mkdir(exist_ok=True)

        preflight = PreflightReport(
            preflight_id="test",
            total=1,
            ok_count=1,
            conflict_count=0,
            skipped_count=0,
            blocked_count=0,
            items=[
                PreflightItem(
                    operation_id="op-missing",
                    source_path=str(missing_source),
                    target_path=str(target),
                    category="documents",
                    status="ok",
                    reason="",
                )
            ],
        )

        result = execute_moves(
            preflight,
            "pkg-001",
            "user-approved-cleanup-abc123",
            True,
            dry_run=False,
        )

        assert result.skipped_count == 1

    def test_conflict_detected(self, tmp_path):
        """대상 파일 존재하면 충돌."""
        source = tmp_path / "file.txt"
        source.write_text("source")

        target_dir = tmp_path / "target"
        target_dir.mkdir()
        target = target_dir / "file.txt"
        target.write_text("existing")

        preflight = PreflightReport(
            preflight_id="test",
            total=1,
            ok_count=1,
            conflict_count=0,
            skipped_count=0,
            blocked_count=0,
            items=[
                PreflightItem(
                    operation_id="op-conflict",
                    source_path=str(source),
                    target_path=str(target),
                    category="documents",
                    status="ok",
                    reason="",
                )
            ],
        )

        result = execute_moves(
            preflight,
            "pkg-001",
            "user-approved-cleanup-abc123",
            True,
            dry_run=False,
        )

        assert result.conflict_count == 1

    def test_user_confirmation_required(self, tmp_path):
        """사용자 확인 필수."""
        preflight = self.create_sample_preflight(tmp_path)

        with pytest.raises(ValueError):
            execute_moves(
                preflight,
                "pkg-001",
                "user-approved-cleanup-abc123",
                False,  # not confirmed
                dry_run=True,
            )

    def test_execution_result_structure(self, tmp_path):
        """실행 결과 구조."""
        preflight = self.create_sample_preflight(tmp_path)

        result = execute_moves(
            preflight,
            "pkg-001",
            "user-approved-cleanup-abc123",
            True,
            dry_run=True,
        )

        assert result.run_id
        assert result.package_id == "pkg-001"
        assert result.timestamp
        assert result.success_count >= 0
        assert len(result.succeeded) >= 0
