"""파일 지도 보고서 빌더.

파일 메타데이터를 종합하여 사용자용 보고서 생성.
추천만 생성하고 실제 정리 작업은 없음.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .models import (
    FileMetadata,
    FileMapReport,
    ScanOptions,
    LARGE_FILE_THRESHOLD_BYTES,
    OLD_FILE_DAYS,
)
from .classifier import FileClassifier
from .duplicate_detector import DuplicateDetector


class FileMapReportBuilder:
    """파일 지도 보고서 빌더."""

    def __init__(self) -> None:
        self.classifier = FileClassifier()
        self.duplicate_detector = DuplicateDetector()

    def build_report(
        self, files: list[FileMetadata], options: ScanOptions, duration_seconds: float
    ) -> FileMapReport:
        """파일 목록으로부터 보고서 생성."""
        # 기본 통계
        total_size = sum(f.size_bytes for f in files)

        # 카테고리별 분류
        by_category = self.classifier.group_by_category(files)
        files_by_category = {
            cat: len(file_list) for cat, file_list in by_category.items()
        }

        # 특수 파일 탐지
        large_files = self._detect_large_files(files)
        old_files = self._detect_old_files(files)
        suspicious_duplicates = self._detect_duplicates(files)
        suspicious_temp = self._detect_suspicious_temp(files)

        # 추천사항 생성
        recommendations = self._generate_recommendations(
            large_files, old_files, suspicious_duplicates, suspicious_temp, files
        )

        return FileMapReport(
            scan_timestamp=datetime.now().isoformat(),
            scanned_directory=options.target_directory,
            scan_duration_seconds=duration_seconds,
            total_files=len(files),
            total_size_bytes=total_size,
            files_by_category=files_by_category,
            large_files=[
                {
                    "path": f.path,
                    "name": f.name,
                    "size_mb": round(f.size_bytes / (1024 * 1024), 2),
                    "modified_time": f.modified_time,
                }
                for f in large_files
            ],
            old_files=[
                {
                    "path": f.path,
                    "name": f.name,
                    "modified_time": f.modified_time,
                    "age_days": self._calculate_age_days(f.modified_time),
                }
                for f in old_files
            ],
            suspicious_duplicates=[
                {
                    "primary": dup.primary_path,
                    "similar": dup.similar_paths,
                    "reason": dup.suspicion_reason,
                    "severity": dup.severity,
                }
                for dup in suspicious_duplicates
            ],
            suspicious_temp=[
                {
                    "path": f.path,
                    "name": f.name,
                    "size_kb": round(f.size_bytes / 1024, 2),
                }
                for f in suspicious_temp
            ],
            recommendations=recommendations,
        )

    @staticmethod
    def _detect_large_files(files: list[FileMetadata]) -> list[FileMetadata]:
        """대용량 파일 탐지."""
        return [f for f in files if f.size_bytes >= LARGE_FILE_THRESHOLD_BYTES]

    @staticmethod
    def _detect_old_files(files: list[FileMetadata]) -> list[FileMetadata]:
        """오래된 파일 탐지."""
        old_date = datetime.now() - timedelta(days=OLD_FILE_DAYS)
        result = []
        for f in files:
            try:
                mod_date = datetime.fromisoformat(f.modified_time)
                if mod_date < old_date:
                    result.append(f)
            except Exception:
                pass
        return result

    def _detect_duplicates(self, files: list[FileMetadata]) -> list:
        """중복 파일 탐지."""
        suspicions = self.duplicate_detector.detect_duplicates(files)
        return suspicions

    def _detect_suspicious_temp(self, files: list[FileMetadata]) -> list[FileMetadata]:
        """임시 파일 탐지."""
        return self.duplicate_detector.detect_suspicious_temp(files)

    @staticmethod
    def _calculate_age_days(timestamp_str: str) -> int:
        """파일 나이 계산 (일 단위)."""
        try:
            mod_date = datetime.fromisoformat(timestamp_str)
            age = datetime.now() - mod_date
            return age.days
        except Exception:
            return 0

    @staticmethod
    def _generate_recommendations(
        large_files: list[FileMetadata],
        old_files: list[FileMetadata],
        duplicates: list,
        temp_files: list[FileMetadata],
        all_files: list[FileMetadata],
    ) -> list[str]:
        """정리 추천사항 생성."""
        recommendations = []

        # 대용량 파일 추천
        if large_files:
            total_large_mb = sum(f.size_bytes for f in large_files) / (1024 * 1024)
            recommendations.append(
                f"대용량 파일({len(large_files)}개, {total_large_mb:.1f}MB): "
                f"아카이브 또는 클라우드 저장소로 이동을 검토하세요."
            )

        # 오래된 파일 추천
        if old_files:
            recommendations.append(
                f"1년 이상 미수정 파일({len(old_files)}개): "
                f"필요 없으면 아카이브로 이동을 검토하세요."
            )

        # 중복 파일 추천
        if duplicates:
            duplicate_count = sum(len(d.similar_paths) for d in duplicates)
            recommendations.append(
                f"중복 의심 파일({duplicate_count}개): "
                f"수동으로 확인하여 중복된 것은 삭제를 검토하세요."
            )

        # 임시 파일 추천
        if temp_files:
            recommendations.append(
                f"임시/다운로드 의심 파일({len(temp_files)}개): "
                f"필요한 것은 정리한 후 나머지는 삭제를 검토하세요."
            )

        # 기본 추천
        if not recommendations:
            recommendations.append("파일 구조가 정리되어 있습니다.")

        # 백분율 통계
        if all_files:
            unknown_count = sum(
                1
                for f in all_files
                if f.extension not in [
                    ext for exts in FileMapReportBuilder._get_all_extensions()
                    for ext in exts
                ]
            )
            if unknown_count > len(all_files) * 0.2:
                recommendations.append(
                    f"분류되지 않은 파일({unknown_count}개): "
                    f"확인하여 정리하세요."
                )

        return recommendations

    @staticmethod
    def _get_all_extensions() -> list[set]:
        """모든 알려진 확장자 반환."""
        from .models import FILE_CATEGORIES
        return list(FILE_CATEGORIES.values())
