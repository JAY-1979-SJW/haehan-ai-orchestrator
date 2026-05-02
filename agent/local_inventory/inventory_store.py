"""로컬 인벤토리 저장소 (JSON 기반).

- JSON 직렬화 저장/로드
- 자동 타임스탬프 추가
- 백업 기능
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_INVENTORY_PATH = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "HaehanAI"
    / "inventory"
    / "local_inventory.json"
)


class InventoryStore:
    """JSON 기반 인벤토리 저장소."""

    def __init__(self, path: Optional[Path] = None):
        """초기화.

        Args:
            path: 저장 경로 (기본값: DEFAULT_INVENTORY_PATH)
        """
        self.path = path or DEFAULT_INVENTORY_PATH

    def save(self, data: dict) -> bool:
        """인벤토리 저장.

        Args:
            data: 저장할 데이터

        Returns:
            성공 여부
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)

            # 타임스탬프 추가
            data["saved_at"] = datetime.utcnow().isoformat() + "Z"

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved inventory to {self.path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save inventory: {e}")
            return False

    def load(self) -> Optional[dict]:
        """인벤토리 로드.

        Returns:
            인벤토리 데이터 또는 None
        """
        try:
            if not self.path.exists():
                logger.info(f"Inventory file not found: {self.path}")
                return None

            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(f"Loaded inventory from {self.path}")
            return data

        except Exception as e:
            logger.error(f"Failed to load inventory: {e}")
            return None

    def exists(self) -> bool:
        """인벤토리 파일 존재 여부."""
        return self.path.exists()

    def get_path(self) -> Path:
        """인벤토리 파일 경로 반환."""
        return self.path

    def backup(self) -> Optional[Path]:
        """백업 파일 생성.

        Returns:
            백업 파일 경로 또는 None
        """
        try:
            if not self.exists():
                logger.warning("Cannot backup non-existent inventory file")
                return None

            backup_path = self.path.with_suffix(".bak")
            backup_path.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")

            logger.info(f"Created backup at {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to backup inventory: {e}")
            return None
