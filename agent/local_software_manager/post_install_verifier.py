"""설치 후 검증 (1D: 카탈로그 기반 verify_commands 실행)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional, List

from .catalog import get_program


@dataclass(frozen=True)
class VerificationResult:
    """검증 결과."""
    program_id: str
    ok: bool  # 모든 명령이 성공했는지
    commands_executed: List[str]
    commands_failed: List[str]
    reboot_may_be_required: bool
    message: str


class PostInstallVerifier:
    """설치 후 검증 엔진."""

    def verify(
        self,
        program_id: str,
        timeout_seconds: int = 10,
    ) -> VerificationResult:
        """설치 후 검증.

        Args:
            program_id: 프로그램 ID
            timeout_seconds: 각 명령 실행 timeout

        Returns:
            VerificationResult
        """
        # 프로그램 정보 조회
        program = get_program(program_id)
        if not program:
            return VerificationResult(
                program_id=program_id,
                ok=False,
                commands_executed=[],
                commands_failed=[],
                reboot_may_be_required=False,
                message='프로그램을 찾을 수 없음',
            )

        # verify_commands 없으면
        if not program.verify_commands:
            return VerificationResult(
                program_id=program_id,
                ok=True,
                commands_executed=[],
                commands_failed=[],
                reboot_may_be_required=program.reboot_may_be_required,
                message='검증 명령이 없음 (경로 확인만)',
            )

        executed = []
        failed = []

        # 각 verify_commands 실행
        for cmd in program.verify_commands:
            if not cmd or cmd == '':
                continue

            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                executed.append(cmd)

                if result.returncode != 0:
                    failed.append(cmd)
            except subprocess.TimeoutExpired:
                executed.append(cmd)
                failed.append(cmd)
            except Exception:
                executed.append(cmd)
                failed.append(cmd)

        # 결과 판정
        all_ok = len(failed) == 0 and len(executed) > 0

        message = ''
        if all_ok:
            message = f'{program.name}이(가) 성공적으로 설치되었습니다.'
        elif len(executed) > 0 and len(failed) > 0:
            message = f'{program.name} 설치 후 일부 검증 명령이 실패했습니다.'
        else:
            message = f'{program.name} 설치 후 검증에 실패했습니다.'

        if program.reboot_may_be_required:
            message += ' 시스템 재부팅이 필요할 수 있습니다.'

        return VerificationResult(
            program_id=program_id,
            ok=all_ok,
            commands_executed=executed,
            commands_failed=failed,
            reboot_may_be_required=program.reboot_may_be_required,
            message=message,
        )
