"""중복 파일 탐지.

파일명, 크기, 패턴 기반 중복 의심 탐지.
파일 내용 비교는 하지 않음 (read 금지).
"""
from __future__ import annotations

from collections import defaultdict
import re

from .models import FileMetadata, DuplicateSuspicion, TEMP_SUSPICION_PATTERNS


class DuplicateDetector:
    """중복 파일 탐지기."""

    def __init__(self) -> None:
        pass

    def detect_duplicates(self, files: list[FileMetadata]) -> list[DuplicateSuspicion]:
        """중복 의심 파일 탐지."""
        duplicates = []

        # 1. 동일 파일명 확인
        by_name = defaultdict(list)
        for f in files:
            by_name[f.name].append(f)

        for name, file_list in by_name.items():
            if len(file_list) > 1:
                primary = file_list[0]
                duplicates.append(
                    DuplicateSuspicion(
                        primary_path=primary.path,
                        similar_paths=[f.path for f in file_list[1:]],
                        suspicion_reason="same_name",
                        severity="high",
                    )
                )

        # 2. 동일 크기 + 유사한 이름
        by_size = defaultdict(list)
        for f in files:
            by_size[f.size_bytes].append(f)

        for size, file_list in by_size.items():
            if len(file_list) > 1 and size > 0:
                # 같은 크기인 파일들이 유사한 이름인지 확인
                for i, primary in enumerate(file_list):
                    similar = []
                    for other in file_list[i + 1 :]:
                        if self._is_similar_name(primary.name, other.name):
                            similar.append(other.path)

                    if similar:
                        duplicates.append(
                            DuplicateSuspicion(
                                primary_path=primary.path,
                                similar_paths=similar,
                                suspicion_reason="same_size",
                                severity="medium",
                            )
                        )

        # 3. Copy/사본/복사본 패턴
        for f in files:
            if self._is_copy_pattern(f.name):
                # 원본 후보 찾기
                base_name = self._extract_base_name(f.name)
                for other in files:
                    if (
                        other.name != f.name
                        and self._extract_base_name(other.name) == base_name
                    ):
                        duplicates.append(
                            DuplicateSuspicion(
                                primary_path=other.path,
                                similar_paths=[f.path],
                                suspicion_reason="copy_pattern",
                                severity="medium",
                            )
                        )
                        break

        return duplicates

    @staticmethod
    def _is_similar_name(name1: str, name2: str) -> bool:
        """두 파일명이 유사한지 확인."""
        base1 = DuplicateDetector._extract_base_name(name1)
        base2 = DuplicateDetector._extract_base_name(name2)
        return base1 == base2

    @staticmethod
    def _extract_base_name(filename: str) -> str:
        """파일명에서 기본명 추출 (복사본/copy 제거)."""
        name = filename
        for pattern in ["_copy", "_사본", "_복사본", " copy", " (", "(복사본"]:
            if pattern in name:
                name = name.split(pattern)[0]
        return name.strip()

    @staticmethod
    def _is_copy_pattern(filename: str) -> bool:
        """파일명이 복사본 패턴인지 확인."""
        patterns = [
            r"_copy\d*",
            r"_사본\d*",
            r"_복사본\d*",
            r"\s*\(\d+\)\.",
            r"\s*copy\d*",
            r"복사본",
        ]
        for pattern in patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                return True
        return False

    def detect_suspicious_temp(
        self, files: list[FileMetadata]
    ) -> list[FileMetadata]:
        """임시/다운로드 의심 파일 탐지."""
        suspicious = []
        for f in files:
            name_lower = f.name.lower()
            for pattern in TEMP_SUSPICION_PATTERNS:
                if pattern.lower() in name_lower:
                    suspicious.append(f)
                    break
        return suspicious
