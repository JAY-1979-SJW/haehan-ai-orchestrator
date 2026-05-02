"""파일 지도 (file_map) 모듈.

사용자 지정 폴더의 파일 메타데이터를 수집하고
분류, 중복 탐지, 정리 추천 등을 제공하는 read-only 시스템.

- 파일 내용 읽기 금지
- 파일 이동/삭제/rename 금지
- 메타데이터만 수집 (경로, 크기, 수정일, 확장자 등)
"""
from .scanner import FileMapScanner
from .classifier import FileClassifier
from .duplicate_detector import DuplicateDetector
from .report_builder import FileMapReportBuilder
from .storage import FileMapStorage

__all__ = [
    "FileMapScanner",
    "FileClassifier",
    "DuplicateDetector",
    "FileMapReportBuilder",
    "FileMapStorage",
]
