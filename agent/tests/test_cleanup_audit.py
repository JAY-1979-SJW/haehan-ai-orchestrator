"""cleanup_audit.py 테스트."""

import json
import pytest
from pathlib import Path

from agent.local_inventory.file_map.cleanup_audit import (
    AuditRecord,
    save_records,
    load_records,
    create_audit_records_from_execution,
)


class TestAuditRecord:
    """AuditRecord 데이터클래스 테스트."""

    def test_audit_record_creation(self):
        """감사 레코드 생성."""
        record = AuditRecord(
            run_id="run-001",
            timestamp="2026-05-02T10:00:00Z",
            package_id="pkg-001",
            operation_id="op-001",
            operation_type="move",
            status="success",
            source_path="C:\\source\\file.txt",
            target_path="C:\\target\\file.txt",
            category="documents",
            risk="low",
            error=None,
        )

        assert record.run_id == "run-001"
        assert record.status == "success"
        assert record.error is None

    def test_audit_record_with_error(self):
        """오류 포함 레코드."""
        record = AuditRecord(
            run_id="run-002",
            timestamp="2026-05-02T10:00:00Z",
            package_id="pkg-001",
            operation_id="op-002",
            operation_type="move",
            status="failed",
            source_path="C:\\source\\missing.txt",
            target_path="C:\\target\\missing.txt",
            category="documents",
            risk="high",
            error="Permission denied",
        )

        assert record.status == "failed"
        assert record.error == "Permission denied"


class TestSaveAndLoadRecords:
    """save_records와 load_records 테스트."""

    def test_save_and_load_single_record(self, tmp_path):
        """단일 레코드 저장 및 로드."""
        audit_file = tmp_path / "audit.jsonl"

        record = AuditRecord(
            run_id="run-001",
            timestamp="2026-05-02T10:00:00Z",
            package_id="pkg-001",
            operation_id="op-001",
            operation_type="move",
            status="success",
            source_path="C:\\source\\file.txt",
            target_path="C:\\target\\file.txt",
            category="documents",
            risk="low",
        )

        save_records([record], audit_file)
        loaded = load_records(audit_file=audit_file)

        assert len(loaded) == 1
        assert loaded[0]["run_id"] == "run-001"
        assert loaded[0]["status"] == "success"

    def test_save_multiple_records(self, tmp_path):
        """여러 레코드 저장."""
        audit_file = tmp_path / "audit.jsonl"

        records = [
            AuditRecord(
                run_id="run-001",
                timestamp="2026-05-02T10:00:00Z",
                package_id="pkg-001",
                operation_id="op-001",
                operation_type="move",
                status="success",
                source_path="C:\\source\\file1.txt",
                target_path="C:\\target\\file1.txt",
                category="documents",
                risk="low",
            ),
            AuditRecord(
                run_id="run-001",
                timestamp="2026-05-02T10:00:00Z",
                package_id="pkg-001",
                operation_id="op-002",
                operation_type="move",
                status="success",
                source_path="C:\\source\\file2.txt",
                target_path="C:\\target\\file2.txt",
                category="spreadsheets",
                risk="low",
            ),
        ]

        save_records(records, audit_file)
        loaded = load_records(audit_file=audit_file)

        assert len(loaded) == 2

    def test_load_by_run_id(self, tmp_path):
        """run_id로 필터링."""
        audit_file = tmp_path / "audit.jsonl"

        records = [
            AuditRecord(
                run_id="run-001",
                timestamp="2026-05-02T10:00:00Z",
                package_id="pkg-001",
                operation_id="op-001",
                operation_type="move",
                status="success",
                source_path="C:\\source\\file1.txt",
                target_path="C:\\target\\file1.txt",
                category="documents",
                risk="low",
            ),
            AuditRecord(
                run_id="run-002",
                timestamp="2026-05-02T10:00:00Z",
                package_id="pkg-002",
                operation_id="op-002",
                operation_type="move",
                status="success",
                source_path="C:\\source\\file2.txt",
                target_path="C:\\target\\file2.txt",
                category="documents",
                risk="low",
            ),
        ]

        save_records(records, audit_file)
        loaded = load_records("run-001", audit_file=audit_file)

        assert len(loaded) == 1
        assert loaded[0]["run_id"] == "run-001"

    def test_load_nonexistent_file(self, tmp_path):
        """없는 파일 로드."""
        audit_file = tmp_path / "nonexistent.jsonl"
        loaded = load_records(audit_file=audit_file)

        assert loaded == []

    def test_load_with_invalid_lines(self, tmp_path):
        """유효하지 않은 라인 건너뛰기."""
        audit_file = tmp_path / "audit.jsonl"

        # 유효한 라인과 유효하지 않은 라인 혼합
        with open(audit_file, "w") as f:
            f.write('{"run_id": "run-001"}\n')
            f.write("invalid json\n")
            f.write('{"run_id": "run-002"}\n')

        loaded = load_records(audit_file=audit_file)
        # 유효한 라인만 로드됨
        assert len(loaded) == 2

    def test_empty_records_list(self, tmp_path):
        """빈 레코드 리스트."""
        audit_file = tmp_path / "audit.jsonl"
        save_records([], audit_file)

        # 파일 생성 안 됨
        assert not audit_file.exists()

    def test_path_masking(self, tmp_path):
        """경로 마스킹."""
        audit_file = tmp_path / "audit.jsonl"

        record = AuditRecord(
            run_id="run-001",
            timestamp="2026-05-02T10:00:00Z",
            package_id="pkg-001",
            operation_id="op-001",
            operation_type="move",
            status="success",
            source_path="C:\\Users\\Secret\\Documents\\file.txt",
            target_path="C:\\backup\\file.txt",
            category="documents",
            risk="low",
        )

        save_records([record], audit_file)
        loaded = load_records(audit_file=audit_file)

        # 경로가 마스킹됨
        assert "[MASKED_PATH]" in loaded[0]["source_path"]
        assert "file.txt" in loaded[0]["source_path"]


class TestCreateAuditRecordsFromExecution:
    """create_audit_records_from_execution 테스트."""

    def test_successful_execution(self):
        """성공한 실행."""
        execution_result = {
            "succeeded": [
                {
                    "operation_id": "op-001",
                    "source_path": "C:\\source\\file.txt",
                    "target_path": "C:\\target\\file.txt",
                    "category": "documents",
                }
            ],
            "failed": [],
            "skipped": [],
            "conflicts": [],
        }

        records = create_audit_records_from_execution(
            "run-001", "pkg-001", execution_result
        )

        assert len(records) == 1
        assert records[0].status == "success"
        assert records[0].operation_type == "move"

    def test_failed_execution(self):
        """실패한 실행."""
        execution_result = {
            "succeeded": [],
            "failed": [
                {
                    "operation_id": "op-001",
                    "source_path": "C:\\source\\file.txt",
                    "target_path": "C:\\target\\file.txt",
                    "error": "Permission denied",
                }
            ],
            "skipped": [],
            "conflicts": [],
        }

        records = create_audit_records_from_execution(
            "run-001", "pkg-001", execution_result
        )

        assert len(records) == 1
        assert records[0].status == "failed"
        assert records[0].error == "Permission denied"

    def test_mixed_execution_results(self):
        """혼합 결과."""
        execution_result = {
            "succeeded": [
                {
                    "operation_id": "op-001",
                    "source_path": "C:\\source\\file1.txt",
                    "target_path": "C:\\target\\file1.txt",
                    "category": "documents",
                }
            ],
            "failed": [
                {
                    "operation_id": "op-002",
                    "source_path": "C:\\source\\file2.txt",
                    "target_path": "C:\\target\\file2.txt",
                    "error": "Permission denied",
                }
            ],
            "skipped": [
                {
                    "operation_id": "op-003",
                    "source_path": "C:\\source\\file3.txt",
                    "target_path": "C:\\target\\file3.txt",
                    "reason": "File not found",
                }
            ],
            "conflicts": [
                {
                    "operation_id": "op-004",
                    "source_path": "C:\\source\\file4.txt",
                    "target_path": "C:\\target\\file4.txt",
                    "reason": "Target exists",
                }
            ],
        }

        records = create_audit_records_from_execution(
            "run-001", "pkg-001", execution_result
        )

        assert len(records) == 4
        statuses = {r.status for r in records}
        assert statuses == {"success", "failed", "skipped", "conflict"}
