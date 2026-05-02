"""휴대용 앱(portable app) 감지기.

Program Files / AppData Local Programs 에서
사용자 지정 폴더의 exe 파일 후보를 메타데이터 기반으로 감지.

read-only: 파일 메타데이터만 수집 (stat), 파일 내용 읽기 금지.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class PortableAppCandidate:
    """휴대용 앱 후보."""
    name: str
    path: str
    size_mb: float
    modified_time: Optional[str] = None
    category_guess: Optional[str] = None


class PortableAppDetector:
    """휴대용 앱 메타데이터 감지."""

    BUILTIN_SEARCH_PATHS = [
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ]

    def __init__(self) -> None:
        self.candidates: list[PortableAppCandidate] = []

    def scan_builtin_paths(self) -> list[PortableAppCandidate]:
        """Program Files 내 exe 후보 스캔."""
        candidates = []
        for path_str in self.BUILTIN_SEARCH_PATHS:
            try:
                path = Path(path_str)
                if path.exists():
                    candidates.extend(self._scan_path(path, max_depth=2))
            except Exception:
                pass
        self.candidates.extend(candidates)
        return candidates

    @staticmethod
    def _scan_path(
        path: Path,
        max_depth: int = 2,
        current_depth: int = 0,
    ) -> list[PortableAppCandidate]:
        """폴더 재귀 스캔 (깊이 제한)."""
        candidates = []

        if current_depth >= max_depth or not path.is_dir():
            return candidates

        try:
            for item in path.iterdir():
                try:
                    if item.is_file() and item.suffix.lower() == ".exe":
                        stat = item.stat()
                        size_mb = stat.st_size / (1024 * 1024)

                        from datetime import datetime
                        mtime = datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat()

                        category = PortableAppDetector._guess_category(item.name)

                        candidates.append(PortableAppCandidate(
                            name=item.stem,
                            path=str(item),
                            size_mb=round(size_mb, 2),
                            modified_time=mtime,
                            category_guess=category,
                        ))
                    elif item.is_dir() and current_depth < max_depth:
                        candidates.extend(
                            PortableAppDetector._scan_path(
                                item, max_depth, current_depth + 1
                            )
                        )
                except Exception:
                    pass
        except Exception:
            pass

        return candidates

    @staticmethod
    def _guess_category(filename: str) -> Optional[str]:
        """exe 파일명에서 카테고리 추측 (휴리스틱)."""
        name_lower = filename.lower()

        if any(x in name_lower for x in ["excel", "xlstart"]):
            return "excel"
        if any(x in name_lower for x in ["hwp", "hancom"]):
            return "hancom"
        if any(x in name_lower for x in ["acad", "autocad"]):
            return "cad"
        if any(x in name_lower for x in ["chrome", "firefox", "edge", "opera"]):
            return "browser"
        if any(x in name_lower for x in ["7z", "winrar", "winzip"]):
            return "archive"
        if any(x in name_lower for x in ["photoshop", "illustrator", "sketch", "affinity"]):
            return "design"

        return None

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화."""
        return {
            "total": len(self.candidates),
            "candidates": [
                {
                    "name": c.name,
                    "path": c.path,
                    "size_mb": c.size_mb,
                    "modified_time": c.modified_time,
                    "category_guess": c.category_guess,
                }
                for c in self.candidates
            ],
        }
