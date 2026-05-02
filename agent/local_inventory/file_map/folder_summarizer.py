"""폴더별 파일 분포 요약기.

상위 폴더들의 파일 분포를 요약하여 업무파일 집중도를 파악.
폴더 메타데이터만 사용, 파일 내용 read 없음.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional
from dataclasses import dataclass

from .models import FILE_CATEGORIES, DEFAULT_EXCLUDED_DIRS


@dataclass
class FolderSummary:
    """폴더별 요약 정보."""
    folder_path: str
    folder_name: str
    direct_file_count: int
    direct_folder_count: int
    total_size_bytes: int
    extension_distribution: dict[str, int]
    last_modified: str
    business_score: float
    business_categories: list[str]


class FolderSummarizer:
    """폴더별 파일 분포 요약기."""

    def __init__(self) -> None:
        self.summaries: list[FolderSummary] = []

    def summarize_top_folders(
        self,
        target_dir: str,
        max_depth: int = 2,
        max_files_per_folder: int = 300,
        total_max_files: int = 10000,
        exclude_hidden: bool = True,
    ) -> tuple[list[FolderSummary], dict]:
        """지정된 루트의 상위 폴더별 파일 분포 요약.

        Args:
            target_dir: 탐색 대상 루트 경로
            max_depth: 최대 탐색 깊이
            max_files_per_folder: 폴더당 최대 파일 수
            total_max_files: 전체 최대 파일 수
            exclude_hidden: 숨겨진 파일/폴더 제외 여부

        Returns:
            (폴더 요약 리스트, 메타 정보)
        """
        self.summaries = []
        start_time = datetime.now()
        total_files_counted = 0
        excluded_dirs = DEFAULT_EXCLUDED_DIRS.copy()

        target = Path(target_dir)
        if not target.exists() or not target.is_dir():
            return [], {
                "ok": False,
                "error": f"Directory not found: {target}",
                "folders_summarized": 0,
            }

        # 루트 자체 및 직접 하위 폴더들 탐색
        self._scan_folder_hierarchy(
            target,
            current_depth=0,
            max_depth=max_depth,
            max_files_per_folder=max_files_per_folder,
            total_max_files=total_max_files,
            total_files_counted=0,
            excluded_dirs=excluded_dirs,
            exclude_hidden=exclude_hidden,
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        return self.summaries, {
            "ok": True,
            "folders_summarized": len(self.summaries),
            "scan_duration_seconds": duration,
        }

    def _scan_folder_hierarchy(
        self,
        folder: Path,
        current_depth: int,
        max_depth: int,
        max_files_per_folder: int,
        total_max_files: int,
        total_files_counted: int,
        excluded_dirs: set[str],
        exclude_hidden: bool,
    ) -> tuple[int, list[FolderSummary]]:
        """폴더 계층 구조 탐색 및 요약 생성."""
        summaries = []

        if current_depth >= max_depth:
            return total_files_counted, summaries

        # 현재 폴더 요약 생성
        if current_depth <= max_depth:
            summary = self._summarize_folder(
                folder,
                max_files_per_folder,
                excluded_dirs,
                exclude_hidden,
            )
            if summary:
                summaries.append(summary)
                self.summaries.append(summary)
                total_files_counted += summary.direct_file_count

        # 하위 폴더 탐색
        if current_depth < max_depth and total_files_counted < total_max_files:
            try:
                for item in folder.iterdir():
                    if total_files_counted >= total_max_files:
                        break

                    if not item.is_dir(follow_symlinks=False):
                        continue

                    if item.name in excluded_dirs:
                        continue

                    if exclude_hidden and item.name.startswith("."):
                        continue

                    _, sub_summaries = self._scan_folder_hierarchy(
                        item,
                        current_depth + 1,
                        max_depth,
                        max_files_per_folder,
                        total_max_files,
                        total_files_counted,
                        excluded_dirs,
                        exclude_hidden,
                    )
                    summaries.extend(sub_summaries)
                    total_files_counted += len(sub_summaries)

            except PermissionError:
                pass
            except Exception:
                pass

        return total_files_counted, summaries

    def _summarize_folder(
        self,
        folder: Path,
        max_files_per_folder: int,
        excluded_dirs: set[str],
        exclude_hidden: bool,
    ) -> Optional[FolderSummary]:
        """단일 폴더 요약 생성."""
        direct_files = []
        direct_folders = []
        extension_counts = defaultdict(int)
        total_size = 0
        last_modified = None

        try:
            for item in folder.iterdir():
                if len(direct_files) >= max_files_per_folder:
                    break

                if exclude_hidden and item.name.startswith("."):
                    continue

                if item.is_dir(follow_symlinks=False):
                    if item.name not in excluded_dirs:
                        direct_folders.append(item.name)
                elif item.is_file(follow_symlinks=False):
                    direct_files.append(item.name)
                    try:
                        stat = item.stat(follow_symlinks=False)
                        total_size += stat.st_size
                        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
                        if last_modified is None or mtime > last_modified:
                            last_modified = mtime
                        ext = item.suffix.lower()
                        if ext:
                            extension_counts[ext] += 1
                        else:
                            extension_counts["[no_ext]"] += 1
                    except OSError:
                        pass

        except PermissionError:
            return None
        except Exception:
            return None

        if not direct_files and not direct_folders:
            return None

        if last_modified is None:
            last_modified = datetime.now().isoformat()

        # 업무 후보 점수 계산
        business_score, categories = self._calculate_business_score(extension_counts)

        return FolderSummary(
            folder_path=str(folder),
            folder_name=folder.name or str(folder),
            direct_file_count=len(direct_files),
            direct_folder_count=len(direct_folders),
            total_size_bytes=total_size,
            extension_distribution=dict(extension_counts),
            last_modified=last_modified,
            business_score=business_score,
            business_categories=categories,
        )

    def _calculate_business_score(
        self,
        extension_counts: dict[str, int],
    ) -> tuple[float, list[str]]:
        """업무파일 점수 계산."""
        score = 0.0
        categories = []

        # 카테고리별 파일 수 집계
        category_counts = defaultdict(int)
        for ext, count in extension_counts.items():
            for category, exts in FILE_CATEGORIES.items():
                if ext in exts:
                    category_counts[category] += count
                    break

        # 카테고리별 점수 계산
        if category_counts.get("document", 0) > 0:
            doc_count = category_counts["document"]
            score += min(doc_count * 0.5, 20)
            categories.append("document")

        if category_counts.get("spreadsheet", 0) > 0:
            sheet_count = category_counts["spreadsheet"]
            score += min(sheet_count * 0.5, 20)
            categories.append("spreadsheet")

        if category_counts.get("cad", 0) > 0:
            cad_count = category_counts["cad"]
            score += min(cad_count * 1.0, 20)
            categories.append("cad")

        if category_counts.get("code", 0) > 0:
            code_count = category_counts["code"]
            score += min(code_count * 0.3, 10)
            categories.append("code")

        if category_counts.get("image", 0) > 0:
            img_count = category_counts["image"]
            score += min(img_count * 0.2, 10)

        return min(score, 100.0), categories
