"""로컬 인벤토리 기본 스모크 테스트."""
from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from agent.local_inventory import LocalInventory
from agent.local_inventory.policy import (
    is_allowed_extension,
    is_allowed_path,
    is_excluded_folder,
    get_max_depth,
)
from agent.local_inventory.metadata import get_file_metadata


class TestLocalInventoryPolicy(unittest.TestCase):
    """정책 테스트."""

    def test_allowed_extensions(self):
        """허용 확장자 테스트."""
        self.assertTrue(is_allowed_extension("file.hwp"))
        self.assertTrue(is_allowed_extension("file.exe"))
        self.assertTrue(is_allowed_extension("file.dll"))
        self.assertFalse(is_allowed_extension("file.bat"))
        self.assertFalse(is_allowed_extension("file.ps1"))

    def test_excluded_folders(self):
        """제외 폴더 테스트."""
        self.assertTrue(is_excluded_folder(".git"))
        self.assertTrue(is_excluded_folder("__pycache__"))
        self.assertTrue(is_excluded_folder("node_modules"))
        self.assertFalse(is_excluded_folder("Documents"))

    def test_allowed_paths(self):
        """허용 경로 테스트."""
        self.assertTrue(is_allowed_path(r"C:\Users\test\Documents"))
        self.assertTrue(is_allowed_path(r"C:\Program Files\Hancom"))
        self.assertFalse(is_allowed_path(r"C:\Windows\System32"))
        self.assertFalse(is_allowed_path(r"C:\ProgramData"))

    def test_max_depth(self):
        """최대 깊이 테스트."""
        self.assertEqual(get_max_depth("program_files"), 2)
        self.assertEqual(get_max_depth("user_documents"), 3)
        self.assertEqual(get_max_depth("registry"), 1)


class TestLocalInventoryMetadata(unittest.TestCase):
    """메타데이터 수집 테스트."""

    def test_file_metadata(self):
        """파일 메타데이터 조회."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_file = f.name
            f.write(b"test content")

        try:
            metadata = get_file_metadata(temp_file)
            self.assertTrue(metadata["exists"])
            self.assertEqual(metadata["size_bytes"], 12)
            self.assertIsNotNone(metadata["modified_time"])
        finally:
            Path(temp_file).unlink()

    def test_file_not_exists(self):
        """존재하지 않는 파일."""
        metadata = get_file_metadata(r"C:\NonExistent\File.txt")
        self.assertFalse(metadata["exists"])
        self.assertIsNone(metadata["size_bytes"])


class TestLocalInventoryStorage(unittest.TestCase):
    """인벤토리 저장소 테스트."""

    def setUp(self):
        """테스트 초기화."""
        self.temp_dir = tempfile.mkdtemp()
        self.inventory = LocalInventory(Path(self.temp_dir))

    def tearDown(self):
        """테스트 정리."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_inventory(self):
        """인벤토리 저장/로드."""
        data = {
            "metadata": {
                "scan_date": "2026-05-02T12:00:00Z",
                "version": "1.0",
            },
            "programs": {
                "hancom": {"installed": False},
            },
        }

        # 저장
        self.assertTrue(self.inventory.save_inventory(data))

        # 로드
        loaded = self.inventory.load_inventory()
        self.assertIsNotNone(loaded)
        self.assertIn("metadata", loaded)
        self.assertIn("programs", loaded)

    def test_db_operations(self):
        """SQLite 데이터베이스 작업."""
        # 초기화
        self.assertTrue(self.inventory.init_db())

        # 프로그램 삽입
        self.assertTrue(
            self.inventory.insert_program(
                "Hancom",
                installed=True,
                version="2014",
                installation_path=r"C:\Program Files\HNC",
            )
        )

        # 프로그램 조회
        program = self.inventory.get_program("Hancom")
        self.assertIsNotNone(program)
        self.assertEqual(program["name"], "Hancom")
        self.assertTrue(program["installed"])
        self.assertEqual(program["version"], "2014")

        # 모든 프로그램 조회
        programs = self.inventory.list_programs()
        self.assertEqual(len(programs), 1)


if __name__ == "__main__":
    unittest.main()
