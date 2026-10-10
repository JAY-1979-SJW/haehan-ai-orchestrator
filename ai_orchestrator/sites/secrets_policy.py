"""사이트별 자격증명/세션 파일 경로 정책.

정책:
- 자격증명: secrets/sites/<site_name>.env
- 세션 상태: secrets/browser_state/<site_name>.json
- secrets/ 하위는 .gitignore 대상 (절대 커밋 금지)
- 환경변수 SECRETS_ROOT / BROWSER_STATE_ROOT 로 override 가능
- 파일이 없어도 graceful: 존재 여부만 boolean 으로 반환
- 평문 자격증명/세션 원문은 이 모듈에서 로그에 찍지 않는다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..core import config  # 기존 config.py 의 루트 유틸 재사용(로깅 설정 등 부수효과 X)


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def _repo_root() -> Path:
    """ai_orchestrator/.. 기준 (패키지 상위).
    config.LOG_DIR 이 override 되어도 repo root 는 패키지 부모로 계산."""
    return Path(config.__file__).resolve().parent.parent


def _env_path(var: str, default: Path) -> Path:
    v = os.environ.get(var, "").strip()
    return Path(v) if v else default


def secrets_root() -> Path:
    return _env_path("SECRETS_ROOT", _repo_root() / "secrets")


def sites_credentials_root() -> Path:
    return _env_path("SITES_CREDENTIALS_ROOT", secrets_root() / "sites")


def browser_state_root() -> Path:
    return _env_path("BROWSER_STATE_ROOT", secrets_root() / "browser_state")


def is_safe_site_name(name: str) -> bool:
    """path traversal 및 예기치 않은 문자 차단."""
    if not name or not isinstance(name, str):
        return False
    return bool(_SAFE_NAME_RE.match(name))


def credentials_path(site_name: str) -> Path:
    if not is_safe_site_name(site_name):
        raise ValueError(f"invalid site_name: {site_name!r}")
    return sites_credentials_root() / f"{site_name}.env"


def session_state_path(site_name: str) -> Path:
    if not is_safe_site_name(site_name):
        raise ValueError(f"invalid site_name: {site_name!r}")
    return browser_state_root() / f"{site_name}.json"


def session_meta_path(site_name: str) -> Path:
    """세션 상태 메타데이터 파일 경로 (쿠키/토큰 원문 미포함)."""
    if not is_safe_site_name(site_name):
        raise ValueError(f"invalid site_name: {site_name!r}")
    return _env_path("SESSION_META_ROOT", secrets_root() / "session_meta") / f"{site_name}.json"


def browser_profile_dir(site_name: str) -> Path:
    """사이트별 Chromium persistent profile 디렉터리 경로."""
    if not is_safe_site_name(site_name):
        raise ValueError(f"invalid site_name: {site_name!r}")
    return _env_path("BROWSER_PROFILE_ROOT", secrets_root() / "browser_profiles") / site_name


def credentials_present(site_name: str) -> bool:
    try:
        return credentials_path(site_name).is_file()
    except ValueError:
        return False


def session_state_present(site_name: str) -> bool:
    try:
        return session_state_path(site_name).is_file()
    except ValueError:
        return False


__all__ = [
    "secrets_root",
    "sites_credentials_root",
    "browser_state_root",
    "is_safe_site_name",
    "credentials_path",
    "session_state_path",
    "session_meta_path",
    "browser_profile_dir",
    "credentials_present",
    "session_state_present",
]
