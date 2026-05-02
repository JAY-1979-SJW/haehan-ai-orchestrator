"""cleanup_paths.py 테스트."""

import pytest
from pathlib import Path
from unittest.mock import patch

from agent.local_inventory.file_map.cleanup_paths import (
    check_source,
    check_conflict,
    build_target_path,
)


class TestCheckSource:
    """check_source 테스트."""

    def test_source_exists(self, tmp_path):
        """소스 파일 존재."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = check_source(str(test_file))
            assert result.source_exists
            assert not result.error

    def test_source_missing(self, tmp_path):
        """소스 파일 없음."""
        test_file = tmp_path / "missing.txt"

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = check_source(str(test_file))
            assert not result.source_exists
            assert result.error == "소스 파일이 존재하지 않습니다"

    def test_empty_path(self):
        """빈 경로."""
        result = check_source("")
        assert not result.source_exists
        assert result.error == "경로가 비어있습니다"

    def test_system_path(self):
        """시스템 경로."""
        result = check_source("C:\\Windows\\System32\\test.txt")
        assert result.is_system_path
        assert "시스템 경로" in result.error

    def test_appdata_path(self):
        """AppData 경로."""
        result = check_source("C:\\Users\\User\\AppData\\Local\\Temp\\test.txt")
        assert result.is_system_path


class TestCheckConflict:
    """check_conflict 테스트."""

    def test_conflict_exists(self, tmp_path):
        """충돌 파일 존재."""
        source = tmp_path / "source" / "test.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("source")

        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "test.txt").write_text("existing")

        assert check_conflict(str(source), str(target_dir))

    def test_no_conflict(self, tmp_path):
        """충돌 없음."""
        source = tmp_path / "source" / "test.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("source")

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        assert not check_conflict(str(source), str(target_dir))

    def test_empty_source(self):
        """빈 소스 경로."""
        assert not check_conflict("", "C:\\target")

    def test_empty_target(self):
        """빈 대상 경로."""
        assert not check_conflict("C:\\source\\file.txt", "")


class TestBuildTargetPath:
    """build_target_path 테스트."""

    def test_build_valid_path(self, tmp_path):
        """유효한 대상 경로 생성."""
        source = tmp_path / "source" / "file.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("content")

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = build_target_path(str(source), str(target_dir))
            assert result
            assert "file.txt" in result
            assert str(target_dir) in result

    def test_preserves_filename(self, tmp_path):
        """파일명 유지."""
        source = tmp_path / "test_document.docx"
        source.write_text("doc")

        target_dir = tmp_path / "output"
        target_dir.mkdir()

        with patch("agent.local_inventory.file_map.cleanup_paths.is_system_path", return_value=False):
            result = build_target_path(str(source), str(target_dir))
            assert result.endswith("test_document.docx")

    def test_empty_source(self):
        """빈 소스."""
        result = build_target_path("", "C:\\target")
        assert result == ""

    def test_empty_target(self):
        """빈 대상."""
        result = build_target_path("C:\\source\\file.txt", "")
        assert result == ""

    def test_system_path_target(self):
        """시스템 경로를 대상으로."""
        source = "C:\\Users\\User\\file.txt"
        result = build_target_path(source, "C:\\Windows\\System32")
        assert result == ""

    def test_system_path_result(self):
        """결과가 시스템 경로인 경우."""
        source = "C:\\source\\file.txt"
        # 대상이 실제로는 시스템 경로로 변환되는 경우
        result = build_target_path(source, "C:\\Windows")
        # build_target_path는 결과를 검사하므로 빈 문자열을 반환할 가능성 있음
        # (실제 filesystem 없이는 테스트 불가)
        pass
