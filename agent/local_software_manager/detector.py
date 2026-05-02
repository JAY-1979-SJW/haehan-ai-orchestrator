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
    _version_cache: dict = {}  # 버전 결과 캐시 (반복 실행 방지)

    @staticmethod
    def check_program(
        program: ProgramDefinition,
        check_version: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """프로그램 설치 여부 확인 (read-only, 경로 중심).

        Args:
            program: 프로그램 정의
            check_version: 버전 명령 실행 여부 (기본값: False, 반복 실행 방지)

        Returns:
            (installed, version, path)

        Note:
            기본은 경로 확인만 (read-only).
            check_version=true일 때만 version_command 실행.
            일단 실행한 version 결과는 캐시됨 (반복 실행 방지).
        """
        # 1. 일반 설치 경로 확인 (read-only, 우선)
        for path_pattern in program.common_paths:
            matched_paths = ProgramDetector._find_paths(path_pattern)
            if matched_paths:
                version = None
                if check_version and program.version_command:
                    version = ProgramDetector._get_version_cached(program.version_command)
                return True, version, matched_paths[0]

        # 2. PATH에서 명령 찾기 (explicit check 요청 시)
        if check_version and program.version_command:
            cmd_name = program.version_command.split()[0]
            in_path = shutil.which(cmd_name)
            if in_path:
                version = ProgramDetector._get_version_cached(program.version_command)
                return True, version, in_path

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
    def _get_version_cached(version_command: str) -> Optional[str]:
        """버전 명령 실행 (캐시됨, 반복 실행 방지).

        timeout 적용, 실패해도 예외 아님.
        같은 명령은 한 세션에서 1회만 실행.
        """
        if not version_command:
            return None

        # 캐시 확인
        if version_command in ProgramDetector._version_cache:
            return ProgramDetector._version_cache[version_command]

        # 첫 실행
        result = ProgramDetector._get_version(version_command)

        # 캐시에 저장
        ProgramDetector._version_cache[version_command] = result

        return result

    @staticmethod
    def _get_version(version_command: str) -> Optional[str]:
        """버전 명령 실행 (내부용, 캐시 없음).

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

    @staticmethod
    def clear_version_cache():
        """버전 캐시 초기화 (테스트 또는 새 세션 시)."""
        ProgramDetector._version_cache.clear()
