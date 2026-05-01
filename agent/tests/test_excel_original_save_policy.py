"""원본 저장 정책 및 승인 테스트."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.excel import approval_policy, backup_manager, original_save_policy


class TestApprovalPolicy(unittest.TestCase):
    """승인 정책 테스트."""

    def test_generate_change_hash(self):
        """변경 hash 생성."""
        change_summary = {
            "total_changes": 5,
            "cell_updates": 2,
            "row_inserts": 1,
            "column_inserts": 1,
            "formula_writes": 1,
        }

        hash_result = approval_policy.generate_change_hash(change_summary)

        self.assertIsNotNone(hash_result)
        self.assertEqual(len(hash_result), 16)

    def test_generate_change_hash_consistency(self):
        """변경 hash 일관성."""
        change_summary = {"total_changes": 5, "cell_updates": 2}

        hash1 = approval_policy.generate_change_hash(change_summary)
        hash2 = approval_policy.generate_change_hash(change_summary)

        self.assertEqual(hash1, hash2)

    def test_validate_approval_token_success(self):
        """승인 토큰 검증 성공."""
        valid, error = approval_policy.validate_approval_token("valid_token_12345")

        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_validate_approval_token_empty(self):
        """빈 토큰 검증 실패."""
        valid, error = approval_policy.validate_approval_token("")

        self.assertFalse(valid)
        self.assertEqual(error, "INVALID_APPROVAL_TOKEN")

    def test_validate_approval_token_none(self):
        """None 토큰 검증 실패."""
        valid, error = approval_policy.validate_approval_token(None)

        self.assertFalse(valid)
        self.assertEqual(error, "INVALID_APPROVAL_TOKEN")

    def test_validate_approval_token_hash_match(self):
        """토큰 hash 일치 검증."""
        expected_hash = "abc123def456"
        token_hash = "abc123def456"

        valid, error = approval_policy.validate_approval_token(
            "token", expected_hash, token_hash
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_validate_approval_token_hash_mismatch(self):
        """토큰 hash 불일치 검증."""
        expected_hash = "abc123def456"
        token_hash = "different_hash"

        valid, error = approval_policy.validate_approval_token(
            "token", expected_hash, token_hash
        )

        self.assertFalse(valid)
        self.assertEqual(error, "HASH_MISMATCH")

    def test_check_document_protection_no_protection(self):
        """보호되지 않은 문서."""
        wb = MagicMock()
        # MagicMock의 MultiUserEditing 기본값때문에 실제 동작 테스트는 real object로 테스트
        # 여기서는 exception이 발생하지 않는지만 확인
        type(wb).ProtectStructure = False
        type(wb).ProtectWindows = False
        type(wb).ReadOnly = False
        type(wb).MultiUserEditing = False

        valid, error = approval_policy.check_document_protection(wb)

        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_check_document_protection_read_only(self):
        """읽기 전용 문서."""
        wb = MagicMock()
        wb.configure_mock(ProtectStructure=False, ProtectWindows=False, ReadOnly=True)

        valid, error = approval_policy.check_document_protection(wb)

        self.assertFalse(valid)
        self.assertEqual(error, "WORKBOOK_READ_ONLY")

    def test_check_document_protection_none(self):
        """None 워크북."""
        valid, error = approval_policy.check_document_protection(None)

        self.assertFalse(valid)
        self.assertEqual(error, "WORKBOOK_NOT_FOUND")

    def test_check_save_readiness_success(self):
        """저장 준비 완료."""
        wb = MagicMock()
        type(wb).ProtectStructure = False
        type(wb).ProtectWindows = False
        type(wb).ReadOnly = False
        type(wb).MultiUserEditing = False

        valid, error = approval_policy.check_save_readiness(
            wb, "token", "hash123"
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_check_save_readiness_no_token(self):
        """토큰 없음."""
        wb = MagicMock()

        valid, error = approval_policy.check_save_readiness(wb, "", "hash")

        self.assertFalse(valid)
        self.assertEqual(error, "INVALID_APPROVAL_TOKEN")

    def test_describe_changes(self):
        """변경 내역 설명 생성."""
        change_summary = {
            "cell_updates": 5,
            "row_inserts": 2,
            "column_inserts": 1,
            "formula_writes": 3,
            "total_changes": 11,
        }

        descriptions = approval_policy.describe_changes(change_summary)

        self.assertTrue(len(descriptions) > 0)
        self.assertIn("셀 수정: 5개", descriptions)


class TestBackupManager(unittest.TestCase):
    """백업 관리자 테스트."""

    def test_generate_backup_path(self):
        """백업 경로 생성."""
        original = "C:\\file.xlsx"

        backup = backup_manager.generate_backup_path(original)

        self.assertIn(".backup.", backup)
        self.assertTrue(backup.endswith(".xlsx"))
        self.assertNotEqual(backup, original)

    def test_generate_backup_path_empty(self):
        """빈 경로."""
        backup = backup_manager.generate_backup_path("")

        self.assertEqual(backup, "")

    def test_create_backup_success(self):
        """백업 생성 성공."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".xlsx") as f:
            f.write("test content")
            original_path = f.name

        try:
            success, error, backup_path = backup_manager.create_backup(original_path)

            self.assertTrue(success)
            self.assertIsNone(error)
            self.assertIsNotNone(backup_path)
            self.assertTrue(os.path.exists(backup_path))

            os.remove(backup_path)
        finally:
            os.remove(original_path)

    def test_create_backup_file_not_found(self):
        """파일 없음."""
        success, error, backup_path = backup_manager.create_backup(
            "/nonexistent/file.xlsx"
        )

        self.assertFalse(success)
        self.assertEqual(error, "ORIGINAL_FILE_NOT_FOUND")
        self.assertIsNone(backup_path)

    def test_verify_backup_success(self):
        """백업 검증 성공."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".xlsx") as f:
            f.write("test content")
            original_path = f.name

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".xlsx") as f:
            f.write("test content")
            backup_path = f.name

        try:
            valid, error = backup_manager.verify_backup(backup_path, original_path)

            self.assertTrue(valid)
            self.assertIsNone(error)
        finally:
            os.remove(original_path)
            os.remove(backup_path)

    def test_verify_backup_not_found(self):
        """백업 파일 없음."""
        valid, error = backup_manager.verify_backup("/nonexistent/backup.xlsx", "/original.xlsx")

        self.assertFalse(valid)
        self.assertEqual(error, "BACKUP_FILE_NOT_FOUND")


class TestOriginalSavePolicy(unittest.TestCase):
    """원본 저장 정책 테스트."""

    def test_save_original_with_backup_no_token(self):
        """토큰 없음."""
        wb = MagicMock()
        result = original_save_policy.save_original_with_backup(
            wb, "C:\\file.xlsx", ""
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "APPROVAL_TOKEN_REQUIRED")

    def test_save_original_with_backup_no_workbook(self):
        """워크북 없음."""
        result = original_save_policy.save_original_with_backup(
            None, "C:\\file.xlsx", "token"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "WORKBOOK_NOT_FOUND")

    def test_save_original_with_backup_no_path(self):
        """경로 없음."""
        wb = MagicMock()
        result = original_save_policy.save_original_with_backup(
            wb, "", "token"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "ORIGINAL_PATH_REQUIRED")

    def test_save_original_with_backup_read_only(self):
        """읽기 전용 문서."""
        wb = MagicMock()
        wb.configure_mock(ProtectStructure=False, ProtectWindows=False, ReadOnly=True)

        result = original_save_policy.save_original_with_backup(
            wb, "C:\\file.xlsx", "token"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "WORKBOOK_READ_ONLY")

    def test_get_backup_info(self):
        """백업 정보 조회."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".xlsx") as f:
            f.write("test content")
            original_path = f.name

        try:
            info = original_save_policy.get_backup_info(original_path)

            self.assertEqual(info["original_path"], original_path)
            self.assertEqual(info["backup_count"], 0)
        finally:
            os.remove(original_path)

    def test_get_backup_info_nonexistent(self):
        """없는 파일의 백업 정보."""
        info = original_save_policy.get_backup_info("/nonexistent/file.xlsx")

        self.assertIsNotNone(info)
        self.assertEqual(info["backup_count"], 0)


if __name__ == "__main__":
    unittest.main()
