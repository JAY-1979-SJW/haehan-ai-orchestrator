"""Docker Desktop 공식 다운로드 모듈 (1D: 단일 프로그램 전용, 사용자 승인 필수)."""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .. import errors as _err


DOCKER_OFFICIAL_URL = "https://www.docker.com/products/docker-desktop/"
DOCKER_DOWNLOAD_URL = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"

DOCKER_ALLOWED_DOMAINS = frozenset({
    'docker.com',
    'desktop.docker.com',
    'docs.docker.com',
})

DOCKER_INSTALLER_ALLOWED_NAMES = frozenset({
    'docker desktop installer.exe',
    'dockerdesktopinstaller.exe',
})

DOCKER_SHORTENER_DOMAINS = frozenset({
    'bit.ly',
    'tinyurl.com',
    'ow.ly',
    'goo.gl',
    'short.link',
})


@dataclass(frozen=True)
class DockerDownloadResult:
    """Docker 다운로드 결과."""
    ok: bool
    installer_path: Optional[str]
    domain_verified: bool
    source: str  # 'official' | 'none'
    next_step: str
    error: Optional[str] = None


class DockerDownloadValidator:
    """Docker 다운로드 URL 검증기."""

    def validate_url(self, url: str) -> tuple[bool, Optional[str]]:
        """다운로드 URL 검증.

        Args:
            url: 다운로드 URL

        Returns:
            (success, error_code)
        """
        if not url or not isinstance(url, str):
            return False, 'docker_download_invalid_url'

        try:
            parsed = urlparse(url)
        except Exception:
            return False, 'docker_download_url_parse_failed'

        # HTTPS만 허용
        if parsed.scheme != 'https':
            return False, 'docker_download_http_not_allowed'

        # 도메인 확인
        netloc = parsed.netloc.lower()
        if not netloc:
            return False, 'docker_download_invalid_domain'

        # 단축 URL 차단
        if netloc in DOCKER_SHORTENER_DOMAINS:
            return False, 'docker_download_shortener_not_allowed'

        # 공식 도메인 확인
        domain_verified = False
        for allowed in DOCKER_ALLOWED_DOMAINS:
            if netloc == allowed or netloc.endswith(f'.{allowed}'):
                domain_verified = True
                break

        if not domain_verified:
            return False, 'docker_download_domain_not_allowed'

        # 파일명 확인 (경로의 마지막 부분)
        # URL decode %20 -> ' '
        filename = urlparse(url).path.split('/')[-1].replace('%20', ' ').lower()
        if not filename or filename not in DOCKER_INSTALLER_ALLOWED_NAMES:
            return False, 'docker_download_filename_not_allowed'

        return True, None


class DockerDownloader:
    """Docker 공식 다운로드 엔진."""

    def __init__(self):
        """Docker 다운로더 초기화."""
        self.validator = DockerDownloadValidator()
        self.download_url = DOCKER_DOWNLOAD_URL

    def download(
        self,
        dest_dir: Optional[str] = None,
        approval_token: str = '',
        user_confirmed_download: bool = False,
    ) -> DockerDownloadResult:
        """Docker Desktop 설치파일 다운로드.

        Args:
            dest_dir: 다운로드 폴더 (기본값: 사용자 Downloads)
            approval_token: 사용자 승인 토큰
            user_confirmed_download: 사용자 명시 확인

        Returns:
            DockerDownloadResult
        """
        # 승인 확인
        if not approval_token or not isinstance(approval_token, str):
            return DockerDownloadResult(
                ok=False,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='승인 토큰 확인 필요',
                error=_err.INSTALL_APPROVAL_REQUIRED,
            )

        if not user_confirmed_download:
            return DockerDownloadResult(
                ok=False,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='사용자 다운로드 확인 필요',
                error='docker_download_user_confirmation_required',
            )

        # 다운로드 폴더 결정
        if not dest_dir:
            dest_dir = str(Path.home() / 'Downloads')

        dest_path = Path(dest_dir)
        if not dest_path.exists():
            dest_path.mkdir(parents=True, exist_ok=True)

        # URL 검증
        valid, error_code = self.validator.validate_url(self.download_url)
        if not valid:
            return DockerDownloadResult(
                ok=False,
                installer_path=None,
                domain_verified=False,
                source='none',
                next_step='다운로드 URL 검증 실패',
                error=error_code,
            )

        # 설치파일명 결정
        filename = Path(self.download_url).name.replace('%20', ' ')
        installer_path = dest_path / filename

        # 다운로드 실행
        try:
            urllib.request.urlretrieve(self.download_url, str(installer_path))
        except Exception as e:
            return DockerDownloadResult(
                ok=False,
                installer_path=None,
                domain_verified=True,
                source='official',
                next_step='다운로드 실패',
                error=f'docker_download_failed:{type(e).__name__}',
            )

        # 다운로드 검증 (파일 존재 + 크기 > 0)
        if not installer_path.exists():
            return DockerDownloadResult(
                ok=False,
                installer_path=None,
                domain_verified=True,
                source='official',
                next_step='다운로드 파일 생성 실패',
                error='docker_download_file_not_found',
            )

        file_size = installer_path.stat().st_size
        if file_size == 0:
            installer_path.unlink()
            return DockerDownloadResult(
                ok=False,
                installer_path=None,
                domain_verified=True,
                source='official',
                next_step='다운로드 파일 크기 0',
                error='docker_download_empty_file',
            )

        # 성공
        return DockerDownloadResult(
            ok=True,
            installer_path=str(installer_path),
            domain_verified=True,
            source='official',
            next_step='다운로드 완료. 설치 실행 전 사용자 승인이 필요합니다.',
        )
