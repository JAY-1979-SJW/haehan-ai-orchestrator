"""파일 정리 계획표 생성기.

local_file_map.json 스캔 결과를 기반으로 정리 계획만 생성.
실제 파일 이동/삭제/rename은 수행하지 않음.

카테고리:
- A. 보관 후보 (오래된 설치파일, ISO/CAB, 1년 이상 미수정, 대용량 압축)
- B. 업무 분류 후보 (문서, 엑셀, CAD, 이미지/스캔, 계약/증빙, 법률)
- C. 중복 검토 후보 (동일/유사 파일명, copy/사본 패턴)
- D. 정리 보류 후보 (미분류, 확장자 없음, 민감정보, 최근 수정)

정책:
- 파일명 기본 마스킹 (PrivacyMasker)
- 제안 경로만 생성 (실제 폴더 생성 금지)
- 원본 계획표 파일 생성 금지
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import re
from collections import defaultdict

from .models import FileMapReport
from .privacy import PrivacyMasker


@dataclass(frozen=True)
class CleanupPlan:
    """정리 계획 항목."""
    file_path: str
    masked_name: str  # 마스킹된 파일명
    category: str  # 보관/업무문서/엑셀/CAD/이미지/민감/중복/보류
    reason: str  # 분류 사유
    proposed_location: str  # 제안 경로
    file_size_bytes: int
    modified_time: str
    confidence: float  # 0.0 ~ 1.0


class CleanupPlanner:
    """파일 정리 계획 생성기."""

    # 설치파일 확장자
    INSTALLER_EXTENSIONS = {
        ".exe", ".msi", ".cab", ".iso", ".dmg", ".pkg",
        ".apk", ".jar", ".zip", ".7z", ".rar"
    }

    # 카테고리별 확장자
    CATEGORY_EXTENSIONS = {
        "document": {".hwp", ".hwpx", ".doc", ".docx", ".pdf", ".txt", ".md"},
        "spreadsheet": {".xls", ".xlsx", ".xlsm", ".csv", ".ods"},
        "cad": {".dwg", ".dxf", ".step", ".stp", ".iges"},
        "image": {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"},
        "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"},
        "audio": {".mp3", ".wav", ".flac", ".aac", ".m4a"},
        "archive": {".zip", ".7z", ".rar", ".tar", ".gz"},
    }

    # 민감정보 패턴
    SENSITIVE_PATTERNS = {
        "신분증", "주민등록증", "운전면허", "여권",
        "통장", "계좌", "급여", "노임",
        "형사", "고소", "소송", "변호인", "법률",
        "개인정보", "증거", "기밀", "계약서"
    }

    # 복사본/중복 패턴
    DUPLICATE_PATTERNS = [
        r"복사본",
        r"사본",
        r"copy",
        r"\(\d+\)$",  # (1), (2) 등
        r"_backup",
        r"_old",
        r"_v\d+",
    ]

    # 최근 파일 기준 (30일)
    RECENT_FILE_DAYS = 30

    def __init__(self, reveal_sensitive_names: bool = False, auth_verified: bool = False):
        """초기화.

        Args:
            reveal_sensitive_names: 민감정보 표시 활성화
            auth_verified: 사용자 인증 완료 여부
        """
        self.reveal_sensitive_names = reveal_sensitive_names
        self.auth_verified = auth_verified
        self.masker = PrivacyMasker()

    def plan_cleanup(self, report: FileMapReport) -> list[CleanupPlan]:
        """정리 계획을 생성한다.

        Args:
            report: 파일 지도 리포트

        Returns:
            정리 계획 항목 리스트
        """
        plans = []

        # 모든 파일 리스트 수집
        all_files = []

        # 대용량 파일
        if report.large_files:
            all_files.extend(report.large_files)

        # 오래된 파일
        if report.old_files:
            all_files.extend(report.old_files)

        # 중복 의심
        if report.suspicious_duplicates:
            all_files.extend(report.suspicious_duplicates)

        # 임시 의심
        if report.suspicious_temp:
            all_files.extend(report.suspicious_temp)

        # 각 파일 분석
        for file_obj in all_files:
            plan = self._analyze_file(file_obj, report.scan_timestamp)
            if plan:
                plans.append(plan)

        # 중복 제거 (동일 경로)
        seen_paths = set()
        unique_plans = []
        for plan in plans:
            if plan.file_path not in seen_paths:
                seen_paths.add(plan.file_path)
                unique_plans.append(plan)

        return unique_plans

    def _analyze_file(self, file_obj: dict, scan_timestamp: str) -> Optional[CleanupPlan]:
        """파일을 분석하여 정리 계획을 생성한다."""
        try:
            path = file_obj.get("path", "")
            name = file_obj.get("name", "")
            size = file_obj.get("size_bytes", 0)
            modified = file_obj.get("modified_time", "")

            if not path or not name:
                return None

            # 마스킹된 파일명
            masked_name = self.masker.render_filename(
                name,
                self.reveal_sensitive_names,
                self.auth_verified
            )

            # 확장자
            ext = self._get_extension(name).lower()

            # 카테고리 결정
            category, reason, proposed_path, confidence = self._categorize_file(
                path, name, ext, size, modified, scan_timestamp
            )

            if category == "skip":
                return None

            return CleanupPlan(
                file_path=path,
                masked_name=masked_name,
                category=category,
                reason=reason,
                proposed_location=proposed_path,
                file_size_bytes=size,
                modified_time=modified,
                confidence=confidence
            )

        except Exception:
            return None

    def _categorize_file(
        self,
        path: str,
        name: str,
        ext: str,
        size: int,
        modified: str,
        scan_timestamp: str
    ) -> tuple[str, str, str, float]:
        """파일을 분류한다.

        Returns:
            (카테고리, 사유, 제안경로, 신뢰도)
        """

        # 1. 보관 후보 (오래된 설치파일)
        if self._is_installer(name, ext):
            if self._is_old_file(modified, scan_timestamp):
                return (
                    "보관",
                    "오래된 설치파일",
                    "01_업무문서/06_설치파일_보관",
                    0.9
                )

        # 2. 민감정보 파일 (우선 분류)
        if self._has_sensitive_pattern(name):
            if self._is_recent_file(modified, scan_timestamp):
                # 최근 민감파일 → 보류
                return (
                    "분류보류",
                    "최근 수정된 민감문서",
                    "99_분류보류",
                    0.8
                )
            else:
                # 오래된 민감파일 → 분리
                return (
                    "민감문서",
                    "민감정보 포함 파일",
                    "01_업무문서/05_계약_증빙_민감",
                    0.95
                )

        # 3. 중복 검토 (파일명 패턴)
        if self._is_duplicate_pattern(name):
            return (
                "중복검토",
                "복사본/중복 의심",
                "01_업무문서/08_중복검토",
                0.7
            )

        # 4. 미분류 파일
        if not ext:
            return (
                "분류보류",
                "확장자 없는 파일",
                "99_분류보류",
                0.5
            )

        # 5. 최근 수정 파일
        if self._is_recent_file(modified, scan_timestamp):
            return (
                "분류보류",
                "최근 수정 파일 (제외됨)",
                "99_분류보류",
                0.3
            )

        # 6. 업무 문서 분류
        category_map = {
            "document": ("업무문서", "01_업무문서", 0.8),
            "spreadsheet": ("엑셀정산", "02_엑셀_내역_정산", 0.8),
            "cad": ("CAD도면", "03_CAD_도면", 0.9),
            "image": ("이미지스캔", "04_사진_스캔", 0.7),
            "video": ("비디오", "07_압축_백업", 0.6),
            "audio": ("오디오", "07_압축_백업", 0.6),
            "archive": ("압축파일", "07_압축_백업", 0.7),
        }

        for cat_name, (disp_name, path_name, conf) in category_map.items():
            if ext in self.CATEGORY_EXTENSIONS.get(cat_name, set()):
                return (
                    disp_name,
                    f"{cat_name} 파일",
                    f"01_업무문서/{path_name}",
                    conf
                )

        # 7. 대용량 파일 (정리 보류)
        if size > 1024 * 1024 * 500:  # 500MB 이상
            return (
                "분류보류",
                "대용량 파일",
                "99_분류보류",
                0.5
            )

        # 기본: 미분류
        return (
            "분류보류",
            "미분류",
            "99_분류보류",
            0.3
        )

    def _get_extension(self, name: str) -> str:
        """파일 확장자 추출."""
        if "." in name:
            return "." + name.rsplit(".", 1)[-1]
        return ""

    def _is_installer(self, name: str, ext: str) -> bool:
        """설치파일 판별."""
        if ext.lower() in self.INSTALLER_EXTENSIONS:
            return True
        installer_keywords = {"setup", "installer", "install"}
        return any(kw in name.lower() for kw in installer_keywords)

    def _is_old_file(self, modified: str, scan_timestamp: str, days: int = 365) -> bool:
        """오래된 파일 판별 (기본 1년)."""
        try:
            mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            scan_dt = datetime.fromisoformat(scan_timestamp.replace("Z", "+00:00"))
            age_days = (scan_dt - mod_dt).days
            return age_days >= days
        except Exception:
            return False

    def _is_recent_file(self, modified: str, scan_timestamp: str, days: int = 30) -> bool:
        """최근 파일 판별 (기본 30일)."""
        try:
            mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            scan_dt = datetime.fromisoformat(scan_timestamp.replace("Z", "+00:00"))
            age_days = (scan_dt - mod_dt).days
            return age_days <= days
        except Exception:
            return False

    def _has_sensitive_pattern(self, name: str) -> bool:
        """민감정보 패턴 검사."""
        name_lower = name.lower()
        return any(pattern.lower() in name_lower for pattern in self.SENSITIVE_PATTERNS)

    def _is_duplicate_pattern(self, name: str) -> bool:
        """중복 패턴 검사."""
        for pattern in self.DUPLICATE_PATTERNS:
            if re.search(pattern, name, re.IGNORECASE):
                return True
        return False

    def summarize_plans(self, plans: list[CleanupPlan]) -> dict:
        """정리 계획 요약.

        Args:
            plans: 정리 계획 리스트

        Returns:
            카테고리별 요약
        """
        summary = defaultdict(lambda: {"count": 0, "total_size": 0, "samples": []})

        for plan in plans:
            cat = plan.category
            summary[cat]["count"] += 1
            summary[cat]["total_size"] += plan.file_size_bytes
            if len(summary[cat]["samples"]) < 30:
                summary[cat]["samples"].append(plan)

        return dict(summary)


def format_size(size_bytes: int) -> str:
    """파일 크기를 읽기 좋은 형식으로 변환."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
