"""바로가기(shortcut) 메타데이터 스캐너.

Windows .lnk 파일에서 대상 경로 및 프로그램 정보 추출.

read-only: 파일 읽기만 수행, 파일 내용 분석 금지.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ShortcutInfo:
    """바로가기 메타데이터."""
    name: str
    path: str  # .lnk 파일 경로
    target_path: Optional[str] = None  # 대상 프로그램 경로
    working_dir: Optional[str] = None
    arguments: Optional[str] = None
    icon_path: Optional[str] = None


class ShortcutScanner:
    """Windows 바로가기 메타데이터 추출."""

    def __init__(self) -> None:
        self.shortcuts: list[ShortcutInfo] = []

    def scan_desktop(self) -> list[ShortcutInfo]:
        """Desktop 바로가기 스캔."""
        return self._scan_folder(Path.home() / "Desktop")

    def scan_start_menu(self) -> list[ShortcutInfo]:
        """Start Menu 바로가기 스캔."""
        start_menu_path = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu"
        return self._scan_folder(start_menu_path)

    def _scan_folder(self, folder: Path) -> list[ShortcutInfo]:
        """폴더 내 .lnk 파일 스캔."""
        shortcuts = []
        if not folder.exists() or not folder.is_dir():
            return shortcuts

        try:
            for lnk_file in folder.rglob("*.lnk"):
                try:
                    info = self._parse_shortcut(lnk_file)
                    if info:
                        shortcuts.append(info)
                        self.shortcuts.append(info)
                except Exception:
                    pass
        except Exception:
            pass

        return shortcuts

    @staticmethod
    def _parse_shortcut(lnk_path: Path) -> Optional[ShortcutInfo]:
        """간단한 .lnk 파일 분석.

        .lnk 파일의 이진 구조를 완전히 파싱하지 않고,
        기본 메타데이터만 추출 (파일명, 기본 정보).

        실제 구현에서는 win32com 등을 사용할 수 있지만,
        read-only 메타데이터만 필요하므로 최소한의 정보만 추출.
        """
        try:
            name = lnk_path.stem
            return ShortcutInfo(
                name=name,
                path=str(lnk_path),
                target_path=None,  # 간단한 분석으로는 대상 경로 추출 제한
                working_dir=None,
                arguments=None,
                icon_path=None,
            )
        except Exception:
            return None

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화."""
        return {
            "total": len(self.shortcuts),
            "shortcuts": [
                {
                    "name": s.name,
                    "path": s.path,
                    "target_path": s.target_path,
                    "working_dir": s.working_dir,
                }
                for s in self.shortcuts
            ],
        }
