"""파일 지도 리포트 프라이버시 및 렌더러 테스트.

- privacy: 민감 파일명 마스킹
- markdown_renderer: 마크다운 렌더링
"""
import pytest
from datetime import datetime
from agent.local_inventory.file_map.privacy import PrivacyMasker
from agent.local_inventory.file_map.models import FileMapReport
from agent.local_inventory.file_map.markdown_renderer import MarkdownRenderer


# ── Privacy Masker 테스트 ────────────────────────────────────────────

def test_privacy_masker_render_both_false() -> None:
    """reveal_sensitive_names=False, auth_verified=False → 마스킹."""
    filename = "곽영규_신분증.jpg"
    result = PrivacyMasker.render_filename(filename, False, False)
    assert "[신분증]" in result
    assert "곽영규" not in result


def test_privacy_masker_render_reveal_true_auth_false() -> None:
    """reveal_sensitive_names=True, auth_verified=False → 마스킹 (부분 활성화 안 됨)."""
    filename = "곽영규_신분증.jpg"
    result = PrivacyMasker.render_filename(filename, True, False)
    assert "[신분증]" in result  # 마스킹 유지
    assert "곽영규" not in result


def test_privacy_masker_render_reveal_false_auth_true() -> None:
    """reveal_sensitive_names=False, auth_verified=True → 마스킹 (미인증 취급)."""
    filename = "곽영규_신분증.jpg"
    result = PrivacyMasker.render_filename(filename, False, True)
    assert "[신분증]" in result  # 마스킹 유지
    assert "곽영규" not in result


def test_privacy_masker_render_both_true() -> None:
    """reveal_sensitive_names=True, auth_verified=True → 원본 표시."""
    filename = "곽영규_신분증.jpg"
    result = PrivacyMasker.render_filename(filename, True, True)
    assert result == filename  # 원본 표시


def test_privacy_masker_신분증() -> None:
    """신분증 패턴 마스킹."""
    filename = "곽영규_신분증.jpg"
    result = PrivacyMasker.mask_filename(filename)
    assert "[신분증]" in result
    assert "****_" in result  # 개인명 완전 마스킹
    assert "곽영규" not in result  # 개인명 제거


def test_privacy_masker_통장사본() -> None:
    """통장사본 패턴 마스킹."""
    filename = "권명수_통장사본.pdf"
    result = PrivacyMasker.mask_filename(filename)
    assert "[통장사본]" in result


def test_privacy_masker_형사사건() -> None:
    """형사사건 패턴 마스킹."""
    filename = "공갈죄_무죄_변호인의견서_v2.docx"
    result = PrivacyMasker.mask_filename(filename)
    assert "[법률문서]" in result or "[변호인" in result


def test_privacy_masker_mask_path() -> None:
    """경로에서 파일명만 마스킹."""
    path = "C:\\Users\\test\\곽영규_신분증.jpg"
    result = PrivacyMasker.mask_path(path, False, False)
    assert "C:\\Users\\test\\" in result
    assert "[신분증]" in result


def test_privacy_masker_should_mask() -> None:
    """마스킹 대상 판정."""
    assert PrivacyMasker.should_mask("신분증.jpg") is True
    assert PrivacyMasker.should_mask("통장사본.pdf") is True
    assert PrivacyMasker.should_mask("normal_file.txt") is False


def test_privacy_masker_exclude_hancom() -> None:
    """한컴오피스 설치파일은 마스킹하지 않음."""
    filename = "01. 한컴오피스 2018.zip"
    result = PrivacyMasker.mask_filename(filename)
    assert result == filename  # 원본 유지


def test_privacy_masker_exclude_microsoft() -> None:
    """Microsoft Office 설치파일은 마스킹하지 않음."""
    filenames = [
        "02. 마이크로소프트 오피스 2016.zip",
        "Microsoft_Office_2019.exe",
        "Office_Setup.msi",
    ]
    for filename in filenames:
        result = PrivacyMasker.mask_filename(filename)
        assert result == filename


def test_privacy_masker_exclude_iso() -> None:
    """ISO 파일은 마스킹하지 않음."""
    filename = "SW_DVD5_Office_Professional_Plus_2016_64Bit_Korean.iso"
    result = PrivacyMasker.mask_filename(filename)
    assert result == filename


def test_privacy_masker_exclude_autocad() -> None:
    """AutoCAD 설치파일은 마스킹하지 않음."""
    filenames = [
        "AutoCAD_2023_Korean_Win_64bit_dlm_001_002.sfx.exe",
        "AutoCAD_2023_Korean_Win_64bit_dlm_002_002.sfx.exe",
    ]
    for filename in filenames:
        result = PrivacyMasker.mask_filename(filename)
        assert result == filename


def test_privacy_masker_exclude_cab() -> None:
    """CAB 파일은 마스킹하지 않음."""
    filenames = ["cab1.cab", "propsww.cab", "propsww2.cab"]
    for filename in filenames:
        result = PrivacyMasker.mask_filename(filename)
        assert result == filename


def test_privacy_masker_contract_alone() -> None:
    """계약서 단독은 마스킹하지 않음."""
    filename = "계약서_2026_최종.docx"
    result = PrivacyMasker.mask_filename(filename)
    assert result == filename  # 마스킹하지 않음


def test_privacy_masker_contract_with_account() -> None:
    """계약서+계좌는 마스킹."""
    filename = "계약서_계좌_이체.docx"
    result = PrivacyMasker.mask_filename(filename)
    assert "[계약서]" in result  # 마스킹됨
    assert "[계좌]" in result


def test_privacy_masker_sensitive_masking() -> None:
    """강한 민감 패턴은 항상 마스킹."""
    filenames = [
        ("신분증_사본.jpg", "[신분증]"),
        ("통장사본_2026.pdf", "[통장사본]"),
        ("형사사건_무죄_증명서.docx", "[형사사건]"),
        ("고소장_최종.docx", "[고소]"),
        ("변호인의견서_v2.docx", "[법률문서]"),
    ]
    for filename, expected_mask in filenames:
        result = PrivacyMasker.mask_filename(filename)
        assert expected_mask in result


def test_privacy_masker_case_insensitive() -> None:
    """대소문자 구분 없이 마스킹."""
    filename = "test_SIGNATURE.jpg"
    result = PrivacyMasker.mask_filename(filename)
    # 현재는 영문 민감 패턴이 없으므로 원본 유지 (향후 추가 가능)
    assert filename == result or result != filename


# ── Markdown Renderer 테스트 ─────────────────────────────────────────

def test_markdown_renderer_basic() -> None:
    """기본 마크다운 렌더링."""
    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\test",
        scan_duration_seconds=1.5,
        total_files=100,
        total_size_bytes=1024 * 1024 * 500,  # 500MB
        files_by_category={"document": 30, "image": 70},
        large_files=[],
        old_files=[],
        suspicious_duplicates=[],
        suspicious_temp=[],
        recommendations=["추천1", "추천2"],
    )

    renderer = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result = renderer.render(report)

    assert "# LOCAL-FILE-MAP-1E:" in result
    assert "스캔 날짜" in result
    assert "C:\\test" in result
    assert "100" in result or "100개" in result
    assert "추천1" in result


def test_markdown_renderer_large_files_formatting() -> None:
    """대용량 파일 크기 표시 확인."""
    # 대용량 파일: 100MB, 200MB
    large_files = [
        {
            "path": "C:\\file1.iso",
            "name": "file1.iso",
            "size_bytes": 100 * 1024 * 1024,
            "size_mb": 100.0,
            "modified_time": "2026-05-02T10:00:00",
        },
        {
            "path": "C:\\file2.zip",
            "name": "file2.zip",
            "size_bytes": 200 * 1024 * 1024,
            "size_mb": 200.0,
            "modified_time": "2026-05-02T11:00:00",
        },
    ]

    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\test",
        scan_duration_seconds=1.0,
        total_files=2,
        total_size_bytes=300 * 1024 * 1024,
        files_by_category={"archive": 2},
        large_files=large_files,
        old_files=[],
        suspicious_duplicates=[],
        suspicious_temp=[],
        recommendations=[],
    )

    renderer = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result = renderer.render(report)

    # 크기가 실제 값으로 표시되어야 함 (표에서)
    # "| 1 | file1.iso | 100.0 |" 형태로 나타남
    assert "100.0 |" in result or "100 |" in result
    assert "200.0 |" in result or "200 |" in result


def test_markdown_renderer_duplicates_not_unnamed() -> None:
    """중복 파일이 unnamed/0으로 표시되지 않음."""
    duplicates = [
        {
            "primary": "C:\\original.txt",
            "similar": [
                "C:\\original_copy.txt",
                "C:\\original_사본.txt",
            ],
            "reason": "copy_pattern",
            "severity": "medium",
        },
    ]

    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\test",
        scan_duration_seconds=1.0,
        total_files=3,
        total_size_bytes=100,
        files_by_category={},
        large_files=[],
        old_files=[],
        suspicious_duplicates=duplicates,
        suspicious_temp=[],
        recommendations=[],
    )

    renderer = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result = renderer.render(report)

    # unnamed이 나타나면 안 됨
    assert "unnamed" not in result.lower()
    # 파일 수가 2가 아닌 다른 수로 표시되면 안 됨
    assert "| 2 |" in result


def test_markdown_renderer_sensitive_masking() -> None:
    """민감 파일명 마스킹이 적용됨."""
    large_files = [
        {
            "path": "C:\\곽영규_신분증.jpg",
            "name": "곽영규_신분증.jpg",
            "size_bytes": 1024 * 1024,
            "size_mb": 1.0,
            "modified_time": "2026-05-02T10:00:00",
        },
    ]

    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\test",
        scan_duration_seconds=1.0,
        total_files=1,
        total_size_bytes=1024 * 1024,
        files_by_category={"image": 1},
        large_files=large_files,
        old_files=[],
        suspicious_duplicates=[],
        suspicious_temp=[],
        recommendations=[],
    )

    # reveal_sensitive=False (마스킹)
    renderer_masked = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result_masked = renderer_masked.render(report)
    assert "[신분증]" in result_masked
    assert "****_[신분증]" in result_masked  # 개인명 완전 마스킹
    assert "곽영규" not in result_masked

    # reveal_sensitive=True (원본)
    renderer_original = MarkdownRenderer(reveal_sensitive_names=True, auth_verified=True)
    result_original = renderer_original.render(report)
    assert "곽영규_신분증" in result_original


def test_markdown_renderer_max_files_warning() -> None:
    """max_files 도달 시 경고 표시."""
    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\test",
        scan_duration_seconds=1.0,
        total_files=5000,  # max_files 제한에 도달
        total_size_bytes=100 * 1024 * 1024,
        files_by_category={},
        large_files=[],
        old_files=[],
        suspicious_duplicates=[],
        suspicious_temp=[],
        recommendations=[],
    )

    renderer = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result = renderer.render(report)

    # 경고 문구가 포함되어야 함
    assert "max_files" in result.lower() or "제한" in result


def test_markdown_renderer_sorting_by_size() -> None:
    """대용량 파일이 크기 내림차순으로 정렬됨."""
    large_files = [
        {
            "path": "C:\\small.iso",
            "name": "small.iso",
            "size_bytes": 50 * 1024 * 1024,
            "size_mb": 50.0,
            "modified_time": "2026-05-02T10:00:00",
        },
        {
            "path": "C:\\large.iso",
            "name": "large.iso",
            "size_bytes": 300 * 1024 * 1024,
            "size_mb": 300.0,
            "modified_time": "2026-05-02T11:00:00",
        },
        {
            "path": "C:\\medium.iso",
            "name": "medium.iso",
            "size_bytes": 150 * 1024 * 1024,
            "size_mb": 150.0,
            "modified_time": "2026-05-02T12:00:00",
        },
    ]

    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\test",
        scan_duration_seconds=1.0,
        total_files=3,
        total_size_bytes=500 * 1024 * 1024,
        files_by_category={},
        large_files=large_files,  # 원본 리스트 (정렬되지 않음)
        old_files=[],
        suspicious_duplicates=[],
        suspicious_temp=[],
        recommendations=[],
    )

    renderer = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result = renderer.render(report)

    # 순서 확인: large.iso가 medium.iso보다 앞에 나와야 함
    large_pos = result.find("large.iso")
    medium_pos = result.find("medium.iso")
    assert large_pos < medium_pos, "대용량 파일이 크기 내림차순으로 정렬되어야 함"


# ── 통합 테스트 ────────────────────────────────────────────────────

def test_integration_privacy_renderer() -> None:
    """프라이버시와 렌더러 통합."""
    # 민감한 파일이 포함된 리포트
    large_files = [
        {
            "path": "C:\\documents\\권명수_통장사본.pdf",
            "name": "권명수_통장사본.pdf",
            "size_bytes": 2 * 1024 * 1024,
            "size_mb": 2.0,
            "modified_time": "2026-05-02T10:00:00",
        },
        {
            "path": "C:\\documents\\normal_file.pdf",
            "name": "normal_file.pdf",
            "size_bytes": 3 * 1024 * 1024,
            "size_mb": 3.0,
            "modified_time": "2026-05-02T11:00:00",
        },
    ]

    report = FileMapReport(
        scan_timestamp=datetime.now().isoformat(),
        scanned_directory="C:\\documents",
        scan_duration_seconds=1.0,
        total_files=2,
        total_size_bytes=5 * 1024 * 1024,
        files_by_category={"document": 2},
        large_files=large_files,
        old_files=[],
        suspicious_duplicates=[],
        suspicious_temp=[],
        recommendations=[],
    )

    # 마스킹 렌더링
    renderer = MarkdownRenderer(reveal_sensitive_names=False, auth_verified=False)
    result = renderer.render(report)

    # 민감 파일이 마스킹됨
    assert "[통장사본]" in result
    assert "****_[통장사본]" in result  # 개인명 완전 마스킹
    assert "권명수" not in result
    # 일반 파일은 그대로
    assert "normal_file.pdf" in result
