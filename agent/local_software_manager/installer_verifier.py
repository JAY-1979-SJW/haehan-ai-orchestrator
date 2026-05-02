"""통합 설치파일 검증기 (1D: 카탈로그 기반)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import errors as _err
from .catalog import get_program


class InstallerFileVerifier:
    """설치파일 검증기."""

    def validate_installer_path(self, program_id: str, installer_path: str) -> tuple[bool, Optional[str]]:
        """설치파일 경로 검증.

        Args:
            program_id: 프로그램 ID
            installer_path: 설치파일 경로

        Returns:
            (success, error_code)
        """
        # 프로그램 정보 조회
        program = get_program(program_id)
        if not program:
            return False, _err.INSTALL_PROGRAM_ID_REQUIRED

        # 경로 없으면
        if not installer_path or not isinstance(installer_path, str):
            return False, _err.INSTALL_PROGRAM_ID_REQUIRED

        # 확장자 확인
        if not installer_path.lower().endswith(f'.{program.installer_type}'):
            return False, f'installer_invalid_extension:expected_{program.installer_type}'

        # 파일명 확인 (패턴이 있는 경우)
        filename = Path(installer_path).name.lower()
        if program.expected_filename_patterns:
            found = False
            for pattern in program.expected_filename_patterns:
                if self._match_pattern(filename, pattern):
                    found = True
                    break

            if not found:
                return False, 'installer_name_not_allowed'

        # 파일 존재 확인
        if not Path(installer_path).exists():
            return False, _err.FILE_NOT_FOUND

        # 파일 타입 확인
        if not Path(installer_path).is_file():
            return False, 'installer_not_file'

        return True, None

    @staticmethod
    def _match_pattern(filename: str, pattern: str) -> bool:
        """파일명 패턴 매칭.

        Args:
            filename: 파일명 (lowercase)
            pattern: 패턴 (lowercase, * 와일드카드 지원)

        Returns:
            매칭 여부
        """
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)
