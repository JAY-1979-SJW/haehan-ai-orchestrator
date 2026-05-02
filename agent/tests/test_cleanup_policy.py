"""cleanup_policy.py 테스트."""

import pytest

from agent.local_inventory.file_map.cleanup_policy import (
    is_allowed_group,
    is_always_excluded_group,
    is_sensitive_file,
    is_huge_file,
    is_system_path,
    get_exclusion_reason,
)


class TestIsAllowedGroup:
    """is_allowed_group 테스트."""

    def test_allowed_groups(self):
        """허용 그룹."""
        assert is_allowed_group("documents")
        assert is_allowed_group("spreadsheets")
        assert is_allowed_group("cad")
        assert is_allowed_group("images")
        assert is_allowed_group("archive")

    def test_disallowed_groups(self):
        """비허용 그룹."""
        assert not is_allowed_group("sensitive")
        assert not is_allowed_group("duplicates")
        assert not is_allowed_group("unknown")


class TestIsAlwaysExcludedGroup:
    """is_always_excluded_group 테스트."""

    def test_excluded_groups(self):
        """제외 그룹."""
        assert is_always_excluded_group("sensitive")
        assert is_always_excluded_group("duplicates")
        assert is_always_excluded_group("high_risk")
        assert is_always_excluded_group("hold")
        assert is_always_excluded_group("unknown")

    def test_non_excluded_groups(self):
        """비제외 그룹."""
        assert not is_always_excluded_group("documents")
        assert not is_always_excluded_group("archive")


class TestIsSensitiveFile:
    """is_sensitive_file 테스트."""

    def test_sensitive_patterns(self):
        """민감 패턴."""
        assert is_sensitive_file("신분증_사본.pdf")
        assert is_sensitive_file("주민등록증.jpg")
        assert is_sensitive_file("운전면허증.pdf")
        assert is_sensitive_file("여권사본.pdf")
        assert is_sensitive_file("통장_사본.jpg")
        assert is_sensitive_file("계좌번호.txt")
        assert is_sensitive_file("급여명세서.pdf")
        assert is_sensitive_file("형사사건기록.pdf")
        assert is_sensitive_file("기밀문서.docx")

    def test_case_insensitive(self):
        """대소문자 구분 없음."""
        assert is_sensitive_file("신분증_COPY.pdf")
        assert is_sensitive_file("통장_COPY.jpg")

    def test_non_sensitive_files(self):
        """비민감 파일."""
        assert not is_sensitive_file("report.pdf")
        assert not is_sensitive_file("document.docx")
        assert not is_sensitive_file("")

    def test_empty_string(self):
        """빈 문자열."""
        assert not is_sensitive_file("")


class TestIsHugeFile:
    """is_huge_file 테스트."""

    def test_huge_file(self):
        """1GB 이상."""
        assert is_huge_file(1024 ** 3)
        assert is_huge_file(1024 ** 3 + 1)
        assert is_huge_file(2 * 1024 ** 3)

    def test_normal_file(self):
        """1GB 미만."""
        assert not is_huge_file(1024 ** 3 - 1)
        assert not is_huge_file(100 * 1024 ** 2)
        assert not is_huge_file(0)

    def test_none_value(self):
        """None."""
        assert not is_huge_file(None)


class TestIsSystemPath:
    """is_system_path 테스트."""

    def test_windows_system_paths(self):
        """Windows 시스템 경로."""
        assert is_system_path("C:\\Windows\\System32\\")
        assert is_system_path("C:\\Program Files\\App\\")
        assert is_system_path("C:\\Program Files (x86)\\App\\")

    def test_appdata_paths(self):
        """AppData 경로."""
        assert is_system_path("C:\\Users\\User\\AppData\\Local\\Temp\\")

    def test_dev_paths(self):
        """개발 경로."""
        assert is_system_path("C:\\Project\\.git\\")
        assert is_system_path("C:\\Project\\node_modules\\")
        assert is_system_path("C:\\Project\\venv\\")

    def test_user_paths(self):
        """사용자 경로."""
        assert not is_system_path("C:\\Users\\User\\Documents\\")
        assert not is_system_path("C:\\Users\\User\\Desktop\\")
        assert not is_system_path("D:\\Data\\Projects\\")

    def test_empty_path(self):
        """빈 경로."""
        assert not is_system_path("")


class TestGetExclusionReason:
    """get_exclusion_reason 테스트."""

    def test_sensitive_excluded(self):
        """민감 그룹 제외 사유."""
        reason = get_exclusion_reason("sensitive", include_sensitive=False)
        assert reason == "민감문서 기본 제외"

    def test_sensitive_included(self):
        """민감 그룹 포함 시."""
        reason = get_exclusion_reason("sensitive", include_sensitive=True)
        assert reason is None

    def test_duplicates_excluded(self):
        """중복 그룹 제외 사유."""
        reason = get_exclusion_reason("duplicates")
        assert "중복" in reason

    def test_allowed_group_no_reason(self):
        """허용 그룹은 제외 사유 없음."""
        reason = get_exclusion_reason("documents")
        assert reason is None

    def test_high_risk_excluded(self):
        """고위험 그룹."""
        reason = get_exclusion_reason("high_risk")
        assert reason is not None
