"""파일 지도 저장소.

JSON 기반 파일 지도 저장 및 로드.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import asdict

from .models import FileMapReport


class FileMapStorage:
    """파일 지도 저장소."""

    DEFAULT_STORAGE_DIR = Path.home() / "AppData" / "Local" / "HaehanAI" / "inventory"

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = storage_dir or self.DEFAULT_STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_report(
        self, report: FileMapReport, filename: str = "local_file_map.json"
    ) -> Path:
        """보고서를 JSON으로 저장."""
        filepath = self.storage_dir / filename

        # dataclass를 dict로 변환
        report_dict = asdict(report)

        # JSON 저장
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        return filepath

    def load_report(self, filename: str = "local_file_map.json") -> Optional[dict]:
        """저장된 보고서를 로드."""
        filepath = self.storage_dir / filename

        if not filepath.exists():
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_storage_info(self) -> dict[str, Any]:
        """저장소 정보 반환."""
        reports = list(self.storage_dir.glob("local_file_map*.json"))
        return {
            "storage_dir": str(self.storage_dir),
            "exists": self.storage_dir.exists(),
            "reports_count": len(reports),
            "reports": [r.name for r in reports],
        }
