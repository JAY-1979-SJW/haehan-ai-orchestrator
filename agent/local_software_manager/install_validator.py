"""설치 실행 요청 검증 (승인토큰, 프로그램ID, 허용목록)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import errors as _err


INSTALL_ALLOWLIST = frozenset({
    'docker', 'git', 'python', 'node', 'chrome', 'vscode',
    'hancom', 'office', 'autocad',
})


@dataclass(frozen=True)
class ValidationResult:
    """검증 결과."""
    ok: bool
    error: Optional[str] = None


class InstallRequestValidator:
    """설치 실행 요청 검증기."""

    def validate(self, request: dict) -> ValidationResult:
        """설치 실행 요청 검증.

        Args:
            request: {'program_id': str, 'approval_token': str, ...}

        Returns:
            ValidationResult
        """
        # approval_token 확인
        approval_token = request.get('approval_token')
        if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
            return ValidationResult(
                ok=False,
                error=_err.INSTALL_APPROVAL_REQUIRED,
            )

        # program_id 확인
        program_id = request.get('program_id')
        if not program_id or not isinstance(program_id, str) or not program_id.strip():
            return ValidationResult(
                ok=False,
                error=_err.INSTALL_PROGRAM_ID_REQUIRED,
            )

        # allowlist 확인
        if program_id not in INSTALL_ALLOWLIST:
            return ValidationResult(
                ok=False,
                error=_err.INSTALL_NOT_IN_ALLOWLIST,
            )

        return ValidationResult(ok=True)
