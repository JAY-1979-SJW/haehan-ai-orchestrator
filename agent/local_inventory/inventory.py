"""로컬 인벤토리 저장/로드 (JSON, SQLite).

- JSON으로 인벤토리 저장
- SQLite로 빠른 검색 지원
- 변경 감지 (timestamp)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 기본 저장 경로: %APPDATA%\haehan-ai-orchestrator\inventory
DEFAULT_INVENTORY_DIR = Path.home() / "AppData" / "Local" / "haehan-ai-orchestrator" / "inventory"


class LocalInventory:
    """로컬 인벤토리 관리자."""

    def __init__(self, inventory_dir: Optional[Path] = None):
        """초기화.

        Args:
            inventory_dir: 인벤토리 저장 경로 (기본값: %APPDATA%/...)
        """
        self.inventory_dir = inventory_dir or DEFAULT_INVENTORY_DIR
        self.inventory_dir.mkdir(parents=True, exist_ok=True)

        self.json_file = self.inventory_dir / "inventory.json"
        self.db_file = self.inventory_dir / "inventory.db"

        logger.info(f"Inventory dir: {self.inventory_dir}")

    def save_inventory(self, data: dict) -> bool:
        """인벤토리를 JSON으로 저장.

        Args:
            data: 인벤토리 데이터

        Returns:
            성공 여부
        """
        try:
            # 메타데이터 추가
            data["metadata"] = data.get("metadata", {})
            data["metadata"]["saved_time"] = datetime.utcnow().isoformat() + "Z"

            # JSON 저장
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved inventory to {self.json_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save inventory: {e}")
            return False

    def load_inventory(self) -> Optional[dict]:
        """인벤토리를 JSON에서 로드.

        Returns:
            인벤토리 데이터 또는 None
        """
        try:
            if not self.json_file.exists():
                logger.info(f"Inventory file not found: {self.json_file}")
                return None

            with open(self.json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(f"Loaded inventory from {self.json_file}")
            return data

        except Exception as e:
            logger.error(f"Failed to load inventory: {e}")
            return None

    def init_db(self) -> bool:
        """SQLite 데이터베이스 초기화.

        Returns:
            성공 여부
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            # 프로그램 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS programs (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    installed INTEGER,
                    version TEXT,
                    installation_path TEXT,
                    last_modified TEXT,
                    last_scanned TEXT
                )
            """)

            # 폴더 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE,
                    file_count INTEGER,
                    folder_count INTEGER,
                    total_size_bytes INTEGER,
                    last_modified TEXT,
                    last_scanned TEXT
                )
            """)

            # 문서 타입 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS doc_types (
                    id INTEGER PRIMARY KEY,
                    folder_id INTEGER,
                    extension TEXT,
                    count INTEGER,
                    FOREIGN KEY (folder_id) REFERENCES folders (id)
                )
            """)

            conn.commit()
            conn.close()

            logger.info(f"Initialized database: {self.db_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to init database: {e}")
            return False

    def insert_program(
        self,
        name: str,
        installed: bool,
        version: Optional[str] = None,
        installation_path: Optional[str] = None,
    ) -> bool:
        """프로그램 정보 저장.

        Args:
            name: 프로그램명
            installed: 설치 여부
            version: 버전
            installation_path: 설치 경로

        Returns:
            성공 여부
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO programs
                (name, installed, version, installation_path, last_scanned)
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                1 if installed else 0,
                version,
                installation_path,
                datetime.utcnow().isoformat() + "Z",
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Failed to insert program {name}: {e}")
            return False

    def get_program(self, name: str) -> Optional[dict]:
        """프로그램 정보 조회.

        Args:
            name: 프로그램명

        Returns:
            프로그램 정보 또는 None
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM programs WHERE name = ?", (name,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "id": row[0],
                "name": row[1],
                "installed": bool(row[2]),
                "version": row[3],
                "installation_path": row[4],
                "last_modified": row[5],
                "last_scanned": row[6],
            }

        except Exception as e:
            logger.error(f"Failed to get program {name}: {e}")
            return None

    def list_programs(self) -> list[dict]:
        """모든 프로그램 조회.

        Returns:
            프로그램 목록
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM programs ORDER BY name")
            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "installed": bool(row[2]),
                    "version": row[3],
                    "installation_path": row[4],
                    "last_modified": row[5],
                    "last_scanned": row[6],
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to list programs: {e}")
            return []

    def get_inventory_json_path(self) -> Path:
        """JSON 인벤토리 파일 경로 반환."""
        return self.json_file

    def get_inventory_db_path(self) -> Path:
        """SQLite 데이터베이스 파일 경로 반환."""
        return self.db_file
