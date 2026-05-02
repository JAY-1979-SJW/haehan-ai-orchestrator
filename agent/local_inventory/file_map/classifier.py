"""파일 분류 엔진.

확장자 기반 파일 분류.
"""
from __future__ import annotations

from .models import FileMetadata, FileClassification, FILE_CATEGORIES


class FileClassifier:
    """파일 분류기."""

    def __init__(self) -> None:
        self.categories = FILE_CATEGORIES

    def classify(self, file_meta: FileMetadata) -> FileClassification:
        """파일을 분류."""
        category = self._find_category(file_meta.extension)

        return FileClassification(
            file_path=file_meta.path,
            category=category,
            confidence=1.0 if category != "unknown" else 0.0,
            notes=None,
        )

    def _find_category(self, extension: str) -> str:
        """확장자로부터 카테고리 찾기."""
        for category, extensions in self.categories.items():
            if extension in extensions:
                return category
        return "unknown"

    def classify_batch(self, files: list[FileMetadata]) -> list[FileClassification]:
        """여러 파일 분류."""
        return [self.classify(f) for f in files]

    def group_by_category(
        self, files: list[FileMetadata]
    ) -> dict[str, list[FileMetadata]]:
        """파일을 카테고리별로 그룹화."""
        grouped: dict[str, list[FileMetadata]] = {}

        for file_meta in files:
            category = self._find_category(file_meta.extension)
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(file_meta)

        return grouped
