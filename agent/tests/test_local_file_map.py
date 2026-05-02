"""파일 지도 (file_map) 테스트.

- scanner: 파일 메타데이터 수집
- classifier: 파일 분류
- duplicate_detector: 중복 탐지
- report_builder: 보고서 생성
- storage: JSON 저장/로드
- action_registry: 액션 등록
- task_executor: 핸들러 연결
"""
import pytest
from pathlib import Path
import tempfile
import json


# ── Models 테스트 ──────────────────────────────────────────────────────

def test_file_metadata_creation() -> None:
    """파일 메타데이터 생성."""
    from agent.local_inventory.file_map.models import FileMetadata

    meta = FileMetadata(
        path="/test/file.txt",
        name="file.txt",
        extension=".txt",
        size_bytes=1024,
        modified_time="2026-05-02T10:00:00",
    )

    assert meta.name == "file.txt"
    assert meta.size_bytes == 1024
    assert meta.extension == ".txt"


def test_scan_options() -> None:
    """스캔 옵션 생성."""
    from agent.local_inventory.file_map.models import ScanOptions

    opts = ScanOptions(
        target_directory="/test",
        scan_depth=2,
        max_files=1000,
    )

    assert opts.target_directory == "/test"
    assert opts.scan_depth == 2
    assert opts.max_files == 1000


# ── Scanner 테스트 ────────────────────────────────────────────────────

def test_file_map_scanner_with_temp_dir() -> None:
    """임시 디렉토리에서 파일 스캔."""
    from agent.local_inventory.file_map import FileMapScanner
    from agent.local_inventory.file_map.models import ScanOptions

    with tempfile.TemporaryDirectory() as tmpdir:
        # 테스트 파일 생성
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("test content")

        # 스캔 실행
        scanner = FileMapScanner()
        options = ScanOptions(target_directory=tmpdir)
        files, info = scanner.scan(options)

        assert info["ok"] is True
        assert len(files) == 1
        assert files[0].name == "test.txt"
        assert files[0].size_bytes > 0


def test_file_map_scanner_respects_max_files() -> None:
    """max_files 제한."""
    from agent.local_inventory.file_map import FileMapScanner
    from agent.local_inventory.file_map.models import ScanOptions

    with tempfile.TemporaryDirectory() as tmpdir:
        # 5개 파일 생성
        for i in range(5):
            Path(tmpdir).joinpath(f"file{i}.txt").write_text(f"content {i}")

        # 최대 3개 파일만 스캔
        scanner = FileMapScanner()
        options = ScanOptions(target_directory=tmpdir, max_files=3)
        files, info = scanner.scan(options)

        assert len(files) <= 3
        assert info["ok"] is True


# ── Classifier 테스트 ────────────────────────────────────────────

def test_file_classifier_document() -> None:
    """문서 파일 분류."""
    from agent.local_inventory.file_map import FileClassifier
    from agent.local_inventory.file_map.models import FileMetadata

    classifier = FileClassifier()
    meta = FileMetadata(
        path="/test.pdf",
        name="test.pdf",
        extension=".pdf",
        size_bytes=1024,
        modified_time="2026-05-02T10:00:00",
    )

    classification = classifier.classify(meta)
    assert classification.category == "document"
    assert classification.confidence == 1.0


def test_file_classifier_unknown() -> None:
    """알려지지 않은 확장자 분류."""
    from agent.local_inventory.file_map import FileClassifier
    from agent.local_inventory.file_map.models import FileMetadata

    classifier = FileClassifier()
    meta = FileMetadata(
        path="/test.xyz",
        name="test.xyz",
        extension=".xyz",
        size_bytes=1024,
        modified_time="2026-05-02T10:00:00",
    )

    classification = classifier.classify(meta)
    assert classification.category == "unknown"
    assert classification.confidence == 0.0


# ── DuplicateDetector 테스트 ────────────────────────────────────────

def test_duplicate_detector_same_name() -> None:
    """동일 파일명 중복 탐지."""
    from agent.local_inventory.file_map import DuplicateDetector
    from agent.local_inventory.file_map.models import FileMetadata

    detector = DuplicateDetector()
    files = [
        FileMetadata("/test1.txt", "test.txt", ".txt", 100, "2026-05-02T10:00:00"),
        FileMetadata("/test2.txt", "test.txt", ".txt", 200, "2026-05-02T11:00:00"),
    ]

    duplicates = detector.detect_duplicates(files)
    assert len(duplicates) > 0
    assert duplicates[0].suspicion_reason == "same_name"


def test_duplicate_detector_suspicious_temp() -> None:
    """임시 파일 탐지."""
    from agent.local_inventory.file_map import DuplicateDetector
    from agent.local_inventory.file_map.models import FileMetadata

    detector = DuplicateDetector()
    files = [
        FileMetadata("/download.zip", "download.zip", ".zip", 1024, "2026-05-02T10:00:00"),
        FileMetadata("/temp_file.txt", "temp_file.txt", ".txt", 512, "2026-05-02T11:00:00"),
    ]

    temp_files = detector.detect_suspicious_temp(files)
    assert len(temp_files) == 2


# ── ReportBuilder 테스트 ────────────────────────────────────────────

def test_report_builder_generates_report() -> None:
    """보고서 생성."""
    from agent.local_inventory.file_map import FileMapReportBuilder
    from agent.local_inventory.file_map.models import FileMetadata, ScanOptions

    builder = FileMapReportBuilder()
    files = [
        FileMetadata("/test.txt", "test.txt", ".txt", 100, "2026-05-02T10:00:00"),
        FileMetadata("/test.pdf", "test.pdf", ".pdf", 500, "2026-05-02T10:00:00"),
    ]
    options = ScanOptions(target_directory="/test")

    report = builder.build_report(files, options, 1.5)

    assert report.total_files == 2
    assert report.total_size_bytes == 600
    assert len(report.recommendations) > 0


# ── Storage 테스트 ────────────────────────────────────────────────────

def test_file_map_storage_save_and_load() -> None:
    """저장 및 로드."""
    from agent.local_inventory.file_map import FileMapStorage, FileMapReportBuilder
    from agent.local_inventory.file_map.models import FileMetadata, ScanOptions

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = Path(tmpdir)
        storage = FileMapStorage(storage_dir)

        # 보고서 생성 및 저장
        builder = FileMapReportBuilder()
        files = [FileMetadata("/test.txt", "test.txt", ".txt", 100, "2026-05-02T10:00:00")]
        options = ScanOptions(target_directory="/test")
        report = builder.build_report(files, options, 1.0)

        saved_path = storage.save_report(report)
        assert saved_path.exists()

        # 로드
        loaded_report = storage.load_report()
        assert loaded_report is not None
        assert loaded_report["total_files"] == 1


# ── Action Registry 테스트 ────────────────────────────────────────────

def test_action_registry_has_file_map_scan() -> None:
    """local_file_map.scan 등록."""
    from agent.action_registry import get_meta, is_known_action

    assert is_known_action("local_file_map.scan")
    meta = get_meta("local_file_map.scan")
    assert meta is not None
    assert meta.risk_level == "medium"
    assert meta.requires_approval is True


def test_action_registry_has_file_map_status() -> None:
    """local_file_map.status 등록."""
    from agent.action_registry import get_meta, is_known_action

    assert is_known_action("local_file_map.status")
    meta = get_meta("local_file_map.status")
    assert meta is not None
    assert meta.risk_level == "low"
    assert meta.requires_approval is False


def test_action_registry_has_file_map_suggest() -> None:
    """local_file_map.suggest 등록."""
    from agent.action_registry import get_meta, is_known_action

    assert is_known_action("local_file_map.suggest")
    meta = get_meta("local_file_map.suggest")
    assert meta is not None
    assert meta.risk_level == "low"
    assert meta.requires_approval is False


# ── Task Executor 테스트 ────────────────────────────────────────────

def test_task_executor_supports_file_map_scan() -> None:
    """file_map.scan 액션 지원."""
    from agent.task_executor import supported_actions

    actions = supported_actions()
    assert "local_file_map.scan" in actions


def test_task_executor_supports_file_map_status() -> None:
    """file_map.status 액션 지원."""
    from agent.task_executor import supported_actions

    actions = supported_actions()
    assert "local_file_map.status" in actions


def test_task_executor_supports_file_map_suggest() -> None:
    """file_map.suggest 액션 지원."""
    from agent.task_executor import supported_actions

    actions = supported_actions()
    assert "local_file_map.suggest" in actions


# ── 안전성 검증 테스트 ────────────────────────────────────────────

def test_no_file_content_reads() -> None:
    """파일 내용 read 없음."""
    import inspect
    from agent.local_inventory.file_map import scanner

    source = inspect.getsource(scanner)
    assert r"\.read()" not in source
    assert r"\.read_text()" not in source
    # write_text는 테스트에서만 사용되므로 제외


def test_no_file_modifications() -> None:
    """파일 수정/삭제/이동 없음."""
    import inspect
    from agent.local_inventory.file_map import scanner

    source = inspect.getsource(scanner)
    assert "unlink()" not in source
    assert "rmdir()" not in source
    assert "rename(" not in source
    assert "replace(" not in source
    assert "move(" not in source


def test_no_subprocess_calls() -> None:
    """프로세스 실행 없음."""
    import inspect
    from agent.local_inventory.file_map import scanner

    source = inspect.getsource(scanner)
    assert "subprocess" not in source
    assert "os.system" not in source
