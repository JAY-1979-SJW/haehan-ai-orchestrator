"""프로그램 설치 상태 감지기."""
from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple
from .catalog import ProgramDefinition, get_catalog


class ProgramDetector:
    """프로그램 설치 상태 감지."""

    VERSION_TIMEOUT = 5  # 초

    @staticmethod
    def check_program(program: ProgramDefinition) -> Tuple[bool, Optional[str], Optional[str]]:
        """프로그램 설치 여부 및 버전 확인.

        Returns:
            (installed, version, path)
        """
        # 1. PATH에서 명령 찾기
        if program.version_command:
            cmd_name = program.version_command.split()[0]
            in_path = shutil.which(cmd_name)
            if in_path:
                version = ProgramDetector._get_version(program.version_command)
                return True, version, in_path

        # 2. 일반 설치 경로 확인
        for path_pattern in program.common_paths:
            matched_paths = ProgramDetector._find_paths(path_pattern)
            if matched_paths:
                version = None
                if program.version_command:
                    version = ProgramDetector._get_version(program.version_command)
                return True, version, matched_paths[0]

        # 3. 찾지 못함
        return False, None, None

    @staticmethod
    def _find_paths(pattern: str) -> list[str]:
        """경로 패턴 매칭.

        예: C:\\Program Files\\Python*\\python.exe
        """
        if '*' not in pattern:
            # 와일드카드 없음: 정확한 경로만 확인
            if os.path.exists(pattern):
                return [pattern]
            return []

        # 와일드카드 포함: glob 패턴 사용
        try:
            path = Path(pattern)
            matches = list(path.parent.glob(path.name))
            return [str(m) for m in matches if m.is_file()]
        except Exception:
            return []

    @staticmethod
    def _get_version(version_command: str) -> Optional[str]:
        """버전 명령 실행.

        timeout 적용, 실패해도 예외 아님.
        """
        if not version_command:
            return None

        try:
            result = subprocess.run(
                version_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=ProgramDetector.VERSION_TIMEOUT
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

            return None

        except subprocess.TimeoutExpired:
            return 'timeout'
        except Exception:
            return None
