"""cleanup_rollback.py 테스트."""

import json
import pytest
from pathlib import Path

from agent.local_inventory.file_map.cleanup_rollback import (
    RollbackEntry,
    RollbackManifest,
    create_manifest,
    save_manifest,
    load_manifest,
)


class TestRollbackEntry:
    """RollbackEntry 데이터클래스 테스트."""

    def test_rollback_entry_creation(self):
        """롤백 항목 생성."""
        entry = RollbackEntry(
            operation_id="op-001",
            original_path="C:\\source\\file.txt",
            moved_to_path="C:\\target\\file.txt",
            rollback_possible=True,
            timestamp="2026-05-02T10:00:00Z",
        )

        assert entry.operation_id == "op-001"
        assert entry.rollback_possible


class TestRollbackManifest:
    """RollbackManifest 데이터클래스 테스트."""

    def test_manifest_creation(self):
        """매니페스트 생성."""
        manifest = RollbackManifest(
            run_id="run-001",
            package_id="pkg-001",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=0,
            entries=[],
        )

        assert manifest.run_id == "run-001"
        assert manifest.total_moved == 0
        assert "수동" in manifest.notes  # Default notes

    def test_default_notes(self):
        """기본 메모."""
        manifest = RollbackManifest(
            run_id="run-001",
            package_id="pkg-001",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=0,
        )

        assert "자동 롤백" in manifest.notes


class TestCreateManifest:
    """create_manifest 테스트."""

    def test_create_from_successful_execution(self):
        """성공한 실행에서 생성."""
        execution_result = {
            "succeeded": [
                {
                    "operation_id": "op-001",
                    "source_path": "C:\\source\\file1.txt",
                    "target_path": "C:\\target\\file1.txt",
                },
                {
                    "operation_id": "op-002",
                    "source_path": "C:\\source\\file2.txt",
                    "target_path": "C:\\target\\file2.txt",
                },
            ],
            "failed": [],
            "skipped": [],
            "conflicts": [],
        }

        manifest = create_manifest("run-001", "pkg-001", execution_result)

        assert manifest.total_moved == 2
        assert len(manifest.entries) == 2
        assert all(e.rollback_possible for e in manifest.entries)

    def test_create_from_mixed_execution(self):
        """혼합 결과에서 생성."""
        execution_result = {
            "succeeded": [
                {
                    "operation_id": "op-001",
                    "source_path": "C:\\source\\file1.txt",
                    "target_path": "C:\\target\\file1.txt",
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
            "skipped": [],
            "conflicts": [],
        }

        manifest = create_manifest("run-001", "pkg-001", execution_result)

        # 성공한 항목만 롤백 항목에 포함
        assert manifest.total_moved == 1
        assert len(manifest.entries) == 1

    def test_empty_succeeded(self):
        """성공한 항목 없음."""
        execution_result = {
            "succeeded": [],
            "failed": [
                {
                    "operation_id": "op-001",
                    "source_path": "C:\\source\\file.txt",
                    "target_path": "C:\\target\\file.txt",
                    "error": "Error",
                }
            ],
            "skipped": [],
            "conflicts": [],
        }

        manifest = create_manifest("run-001", "pkg-001", execution_result)

        assert manifest.total_moved == 0
        assert len(manifest.entries) == 0


class TestSaveAndLoadManifest:
    """save_manifest와 load_manifest 테스트."""

    def test_save_and_load_manifest(self, tmp_path):
        """매니페스트 저장 및 로드."""
        manifest = RollbackManifest(
            run_id="run-001",
            package_id="pkg-001",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=1,
            entries=[
                RollbackEntry(
                    operation_id="op-001",
                    original_path="C:\\source\\file.txt",
                    moved_to_path="C:\\target\\file.txt",
                    rollback_possible=True,
                    timestamp="2026-05-02T10:00:00Z",
                )
            ],
        )

        save_path = save_manifest(manifest, tmp_path)

        assert save_path.exists()
        assert "run-001" in str(save_path)

        # 로드 및 검증
        loaded = load_manifest("run-001", tmp_path)

        assert loaded is not None
        assert loaded["run_id"] == "run-001"
        assert loaded["total_moved"] == 1

    def test_load_nonexistent_manifest(self, tmp_path):
        """없는 매니페스트 로드."""
        loaded = load_manifest("nonexistent", tmp_path)
        assert loaded is None

    def test_save_creates_directory(self, tmp_path):
        """저장 시 디렉토리 생성."""
        manifest = RollbackManifest(
            run_id="run-002",
            package_id="pkg-002",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=0,
        )

        rollback_dir = tmp_path / "new_dir"
        assert not rollback_dir.exists()

        save_manifest(manifest, rollback_dir)

        assert rollback_dir.exists()
        assert (rollback_dir / "rollback_run-002.json").exists()

    def test_manifest_json_structure(self, tmp_path):
        """JSON 구조 검증."""
        manifest = RollbackManifest(
            run_id="run-003",
            package_id="pkg-003",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=1,
            entries=[
                RollbackEntry(
                    operation_id="op-001",
                    original_path="C:\\source\\file.txt",
                    moved_to_path="C:\\target\\file.txt",
                    rollback_possible=True,
                    timestamp="2026-05-02T10:00:00Z",
                )
            ],
        )

        save_path = save_manifest(manifest, tmp_path)

        # 파일 내용 검증
        with open(save_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["run_id"] == "run-003"
        assert data["total_moved"] == 1
        assert len(data["entries"]) == 1
        assert data["entries"][0]["operation_id"] == "op-001"

    def test_load_malformed_json(self, tmp_path):
        """형식 오류 JSON."""
        manifest_file = tmp_path / "rollback_run-004.json"
        manifest_file.write_text("not valid json")

        loaded = load_manifest("run-004", tmp_path)
        assert loaded is None

    def test_multiple_manifests(self, tmp_path):
        """여러 매니페스트."""
        manifest1 = RollbackManifest(
            run_id="run-001",
            package_id="pkg-001",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=0,
        )

        manifest2 = RollbackManifest(
            run_id="run-002",
            package_id="pkg-002",
            generated_at="2026-05-02T10:00:00Z",
            total_moved=0,
        )

        save_manifest(manifest1, tmp_path)
        save_manifest(manifest2, tmp_path)

        loaded1 = load_manifest("run-001", tmp_path)
        loaded2 = load_manifest("run-002", tmp_path)

        assert loaded1 is not None
        assert loaded2 is not None
        assert loaded1["run_id"] != loaded2["run_id"]
