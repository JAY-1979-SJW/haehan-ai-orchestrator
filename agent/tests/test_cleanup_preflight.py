"""cleanup_preflight.py 테스트."""

import pytest
from pathlib import Path
from unittest.mock import patch

from agent.local_inventory.file_map.cleanup_preflight import (
    run_preflight,
)


class TestRunPreflight:
    """run_preflight 테스트."""

    def test_empty_plans(self):
        """빈 계획."""
        result = run_preflight([], "C:\\target")
        assert result.total == 0
        assert result.ok_count == 0

    def test_ok_status(self, tmp_path):
        """사전검사 통과."""
        source = tmp_path / "source" / "document.docx"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("content")

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        plans = [
            {
                "operation_id": "op-001",
                "path": str(source),
                "category": "documents",
                "file_size_bytes": 1024,
                "file_name": "document.docx",
            }
        ]

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = run_preflight(plans, str(target_dir))
            assert result.total == 1
            assert result.ok_count == 1
            assert any(item.status == "ok" for item in result.items)

    def test_blocked_sensitive_file(self, tmp_path):
        """민감 파일 차단."""
        source = tmp_path / "신분증_사본.pdf"
        source.write_text("sensitive")

        plans = [
            {
                "operation_id": "op-002",
                "path": str(source),
                "category": "documents",
                "file_size_bytes": 1024,
                "file_name": "신분증_사본.pdf",
            }
        ]

        result = run_preflight(plans, str(tmp_path / "target"))
        assert result.blocked_count == 1
        assert any(item.status == "blocked" for item in result.items)

    def test_blocked_huge_file(self, tmp_path):
        """대용량 파일 차단."""
        source = tmp_path / "huge.iso"
        source.write_text("x" * 100)

        plans = [
            {
                "operation_id": "op-003",
                "path": str(source),
                "category": "archive",
                "file_size_bytes": 1024 ** 3 + 1,  # 1GB+
                "file_name": "huge.iso",
            }
        ]

        result = run_preflight(plans, str(tmp_path / "target"))
        assert result.blocked_count == 1

    def test_blocked_excluded_group(self, tmp_path):
        """제외 그룹 차단."""
        source = tmp_path / "duplicate.txt"
        source.write_text("content")

        plans = [
            {
                "operation_id": "op-004",
                "path": str(source),
                "category": "duplicates",
                "file_size_bytes": 100,
                "file_name": "duplicate.txt",
            }
        ]

        result = run_preflight(plans, str(tmp_path / "target"))
        assert result.blocked_count == 1

    def test_skipped_missing_source(self, tmp_path):
        """소스 파일 없음 - 스킵."""
        missing_path = str(tmp_path / "missing.txt")

        plans = [
            {
                "operation_id": "op-005",
                "path": missing_path,
                "category": "documents",
                "file_size_bytes": 100,
                "file_name": "missing.txt",
            }
        ]

        result = run_preflight(plans, str(tmp_path / "target"))
        assert result.skipped_count == 1

    def test_conflict_existing_target(self, tmp_path):
        """대상 경로 충돌."""
        source = tmp_path / "source" / "file.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("source content")

        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "file.txt").write_text("existing")

        plans = [
            {
                "operation_id": "op-006",
                "path": str(source),
                "category": "documents",
                "file_size_bytes": 100,
                "file_name": "file.txt",
            }
        ]

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = run_preflight(plans, str(target_dir))
            assert result.conflict_count == 1
            assert any(item.status == "conflict" for item in result.items)

    def test_mixed_statuses(self, tmp_path):
        """혼합 상태."""
        # 성공 항목
        ok_file = tmp_path / "good.txt"
        ok_file.write_text("ok")

        # 민감 항목
        sensitive_file = tmp_path / "신분증.pdf"
        sensitive_file.write_text("sensitive")

        # 누락 항목
        missing_file = str(tmp_path / "missing.txt")

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        plans = [
            {
                "operation_id": "op-ok",
                "path": str(ok_file),
                "category": "documents",
                "file_size_bytes": 100,
                "file_name": "good.txt",
            },
            {
                "operation_id": "op-sensitive",
                "path": str(sensitive_file),
                "category": "documents",
                "file_size_bytes": 100,
                "file_name": "신분증.pdf",
            },
            {
                "operation_id": "op-missing",
                "path": missing_file,
                "category": "documents",
                "file_size_bytes": 100,
                "file_name": "missing.txt",
            },
        ]

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = run_preflight(plans, str(target_dir))
            assert result.total == 3
            assert result.ok_count >= 1
            assert result.blocked_count >= 1
            assert result.skipped_count >= 1

    def test_sensitivity_include_flag(self, tmp_path):
        """민감 파일 포함 플래그."""
        sensitive = tmp_path / "통장_사본.jpg"
        sensitive.write_text("bank")

        plans = [
            {
                "operation_id": "op-007",
                "path": str(sensitive),
                "category": "documents",
                "file_size_bytes": 100,
                "file_name": "통장_사본.jpg",
            }
        ]

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # 민감 파일 기본 제외
        result1 = run_preflight(plans, str(target_dir), include_sensitive=False)
        assert result1.blocked_count == 1

        # 민감 파일 포함 시도 (파일 검사로 여전히 차단)
        result2 = run_preflight(plans, str(target_dir), include_sensitive=True)
        assert result2.blocked_count == 1  # 파일명 패턴으로 차단

    def test_disallowed_group(self, tmp_path):
        """비허용 그룹."""
        file_obj = tmp_path / "file.txt"
        file_obj.write_text("content")

        plans = [
            {
                "operation_id": "op-008",
                "path": str(file_obj),
                "category": "invalid_category",
                "file_size_bytes": 100,
                "file_name": "file.txt",
            }
        ]

        result = run_preflight(plans, str(tmp_path / "target"))
        assert result.blocked_count == 1
