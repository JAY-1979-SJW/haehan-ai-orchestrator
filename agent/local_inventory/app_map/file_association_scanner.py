"""파일 확장자 연결 정보 스캐너 (read-only).

Windows Registry에서 파일 확장자와 프로그램의 연결 관계를 읽음.

대상 확장자:
- .hwp, .hwpx (한컴)
- .xlsx, .xlsm (Excel)
- .dwg, .dxf (AutoCAD)
- .pdf (PDF)
- .ies (조명계산)
- .ldt (조명계산)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class FileAssociation:
    """파일 확장자 연결 정보."""
    extension: str
    associated_program: Optional[str] = None
    associated_program_path: Optional[str] = None
    progid: Optional[str] = None


class FileAssociationScanner:
    """파일 확장자 연결 정보 조회 (Registry read-only)."""

    TRACKED_EXTENSIONS = {
        ".hwp", ".hwpx",  # 한컴
        ".xlsx", ".xlsm",  # Excel
        ".dwg", ".dxf",  # AutoCAD
        ".pdf",  # PDF
        ".ies", ".ldt",  # 조명계산
    }

    def __init__(self) -> None:
        self.associations: dict[str, FileAssociation] = {}

    def scan_associations(self) -> dict[str, FileAssociation]:
        """파일 확장자 연결 정보 스캔."""
        try:
            import winreg
        except ImportError:
            return {}

        for ext in self.TRACKED_EXTENSIONS:
            try:
                self._scan_extension(winreg, ext)
            except Exception:
                pass

        return self.associations

    def _scan_extension(self, winreg: Any, extension: str) -> None:
        """단일 확장자 연결 조회."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, extension, access=winreg.KEY_READ
            ) as key:
                progid, _ = winreg.QueryValueEx(key, "")

                program_name = None
                program_path = None

                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CLASSES_ROOT,
                        f"{progid}\\shell\\open\\command",
                        access=winreg.KEY_READ,
                    ) as cmd_key:
                        program_path, _ = winreg.QueryValueEx(cmd_key, "")
                        program_name = self._extract_program_name(program_path)
                except Exception:
                    pass

                assoc = FileAssociation(
                    extension=extension,
                    associated_program=program_name,
                    associated_program_path=program_path,
                    progid=progid,
                )
                self.associations[extension] = assoc

        except Exception:
            pass

    @staticmethod
    def _extract_program_name(program_path: Optional[str]) -> Optional[str]:
        """프로그램 경로에서 실행파일명 추출."""
        if not program_path:
            return None

        program_path = program_path.strip('"').split('"')[0].strip()

        try:
            from pathlib import Path
            return Path(program_path).stem
        except Exception:
            return None

    def get_association(self, extension: str) -> Optional[FileAssociation]:
        """확장자 연결 정보 조회."""
        return self.associations.get(extension)

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화."""
        return {
            "total": len(self.associations),
            "associations": {
                ext: {
                    "extension": assoc.extension,
                    "associated_program": assoc.associated_program,
                    "progid": assoc.progid,
                }
                for ext, assoc in self.associations.items()
            },
        }
