"""통합 소프트웨어 다운로드 Provider (1D: 카탈로그 기반, 공식 도메인 검증)."""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .. import errors as _err
from .catalog import get_program


SHORTENER_DOMAINS = frozenset({
    'bit.ly',
    'tinyurl.com',
    'ow.ly',
    'goo.gl',
    'short.link',
})


@dataclass(frozen=True)
class DownloadResult:
    """다운로드 결과."""
    ok: bool
    program_id: str
    installer_path: Optional[str]
    domain_verified: bool
    source: str  # 'official' | 'none'
    next_step: str
    error: Optional[str] = None


class DownloadValidator:
    """다운로드 URL 검증기."""

    def validate_url(self, program_id: str, url: str) -> tuple[bool, Optional[str]]:
        """다운로드 URL 검증.

        Args:
            program_id: 프로그램 ID
            url: 다운로드 URL

        Returns:
            (success, error_code)
        """
        # 프로그램 정보 조회
        program = get_program(program_id)
        if not program:
            return False, _err.INSTALL_PROGRAM_ID_REQUIRED

        # URL 유효성 확인
        if not url or not isinstance(url, str):
            return False, 'download_invalid_url'

        try:
            parsed = urlparse(url)
        except Exception:
            return False, 'download_url_parse_failed'

        # HTTPS만 허용
        if parsed.scheme != 'https':
            return False, 'download_http_not_allowed'

        # 도메인 확인
        netloc = parsed.netloc.lower()
        if not netloc:
            return False, 'download_invalid_domain'

        # 단축 URL 차단
        if netloc in SHORTENER_DOMAINS:
            return False, 'download_shortener_not_allowed'

        # 공식 도메인 확인
        domain_verified = False
        for allowed in program.official_domains:
            if netloc == allowed or netloc.endswith(f'.{allowed}'):
                domain_verified = True
                break

        if not domain_verified:
            return False, 'download_domain_not_allowed'

        # 파일명 검증 (패턴이 있는 경우)
        if program.expected_filename_patterns:
            filename = urlparse(url).path.split('/')[-1].replace('%20', ' ').lower()
            if not filename:
                return False, 'download_filename_empty'

            # 패턴 매칭 (와일드카드 지원)
            found = False
            for pattern in program.expected_filename_patterns:
                if self._match_pattern(filename, pattern):
                    found = True
                    break

            if not found:
                return False, 'download_filename_not_allowed'

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


class SoftwareDownloader:
    """공식 다운로드 엔진."""

    def __init__(self):
        """다운로더 초기화."""
        self.validator = DownloadValidator()

    def download(
        self,
        program_id: str,
        download_url: str,
        dest_dir: Optional[str] = None,
        approval_token: str = '',
        user_confirmed_download: bool = False,
    ) -> DownloadResult:
        """소프트웨어 설치파일 다운로드.

        Args:
            program_id: 프로그램 ID
            download_url: 다운로드 URL
            dest_dir: 다운로드 폴더 (기본값: 사용자 Downloads)
            approval_token: 사용자 승인 토큰
            user_confirmed_download: 사용자 명시 확인

        Returns:
            DownloadResult
        """
        # 프로그램 정보 조회
        program = get_program(program_id)
        if not program:
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='프로그램을 찾을 수 없음',
                error=_err.INSTALL_PROGRAM_ID_REQUIRED,
            )

        # 자동 다운로드 지원 확인
        if not program.supports_auto_download:
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step=f'{program.name}은 자동 다운로드를 지원하지 않습니다.',
                error='download_not_supported',
            )

        # 승인 확인
        if not approval_token or not isinstance(approval_token, str):
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='승인 토큰 확인 필요',
                error=_err.INSTALL_APPROVAL_REQUIRED,
            )

        if not user_confirmed_download:
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='사용자 다운로드 확인 필요',
                error='download_user_confirmation_required',
            )

        # 다운로드 폴더 결정
        if not dest_dir:
            dest_dir = str(Path.home() / 'Downloads')

        dest_path = Path(dest_dir)
        if not dest_path.exists():
            dest_path.mkdir(parents=True, exist_ok=True)

        # URL 검증
        valid, error_code = self.validator.validate_url(program_id, download_url)
        if not valid:
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='다운로드 URL 검증 실패',
                error=error_code,
            )

        # 설치파일명 결정
        filename = Path(download_url).name.replace('%20', ' ')
        installer_path = dest_path / filename

        # 다운로드 실행
        try:
            urllib.request.urlretrieve(download_url, str(installer_path))
        except Exception as e:
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=True,
                source='official',
                next_step='다운로드 실패',
                error=f'download_failed:{type(e).__name__}',
            )

        # 다운로드 검증 (파일 존재 + 크기 > 0)
        if not installer_path.exists():
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=True,
                source='official',
                next_step='다운로드 파일 생성 실패',
                error='download_file_not_found',
            )

        file_size = installer_path.stat().st_size
        if file_size == 0:
            installer_path.unlink()
            return DownloadResult(
                ok=False,
                program_id=program_id,
                installer_path=None,
                domain_verified=True,
                source='official',
                next_step='다운로드 파일 크기 0',
                error='download_empty_file',
            )

        # 성공
        return DownloadResult(
            ok=True,
            program_id=program_id,
            installer_path=str(installer_path),
            domain_verified=True,
            source='official',
            next_step=f'{program.name} 다운로드 완료. 설치 실행 전 사용자 승인이 필요합니다.',
        )
