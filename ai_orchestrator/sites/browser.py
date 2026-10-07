"""Playwright 기반 브라우저 실행 최소 래퍼.

이번 단계 목표:
- Playwright 가 설치되어 있지 않아도 import/테스트가 깨지지 않아야 한다.
- storage_state 파일이 있으면 주입 가능한 구조만 만든다.
- 실제로는 브라우저를 열지 않는다 (launch_available 로 가능성만 점검).
- 스크린샷 경로 정책만 정의한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core import config
from . import secrets_policy

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 15_000
DEFAULT_HEADLESS = True

SCREENSHOT_ROOT = config.LOG_DIR / "site_screenshots"


@dataclass
class BrowserLaunchProbe:
    available: bool
    reason: str = ""


def _try_import_playwright() -> tuple[bool, str]:
    try:
        import playwright  # type: ignore  # noqa: F401

        return True, ""
    except Exception as e:  # ImportError + 모듈 부수적 오류 모두 보호  # noqa: BLE001 - playwright 모듈 import 가능 여부 probe - ImportError 등 모든 부수 오류를 캡처해 '사용 불가' 상태로 안전하게 폴백, 실행/위험 조작 없음
        return False, f"playwright import 불가: {type(e).__name__}"


def probe_launch() -> BrowserLaunchProbe:
    """브라우저 기동 가능성만 확인.

    실제 브라우저 프로세스를 띄우지 않는다. import 가능 여부로만 판정한다.
    실제 기동은 향후 단계에서 안전한 컨텍스트로 감싸서 수행.
    """
    ok, reason = _try_import_playwright()
    if not ok:
        return BrowserLaunchProbe(available=False, reason=reason)
    return BrowserLaunchProbe(available=True)


def screenshot_dir(site_name: str) -> Path:
    """사이트별 스크린샷 저장 디렉터리 경로만 반환 (생성은 실제 실행 시점에)."""
    if not secrets_policy.is_safe_site_name(site_name):
        raise ValueError(f"invalid site_name: {site_name!r}")
    return SCREENSHOT_ROOT / site_name


def storage_state_option(site_name: str) -> str | None:
    """context 생성 시 넘길 storage_state 파일 경로. 없으면 None."""
    p = secrets_policy.session_state_path(site_name)
    return str(p) if p.is_file() else None


def save_storage_state(site_name: str, context: Any) -> Path:
    """Playwright context 의 storageState 를 secrets 경로에 저장.

    Args:
        site_name: secrets_policy 기준 사이트 식별자
        context:   Playwright BrowserContext 객체

    Returns:
        저장된 파일의 Path

    Raises:
        ValueError: site_name 이 유효하지 않을 때
    """
    p = secrets_policy.session_state_path(site_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(p))
    logger.info("storageState saved: %s -> %s", site_name, p.name)
    return p


__all__ = [
    "DEFAULT_HEADLESS",
    "DEFAULT_TIMEOUT_MS",
    "SCREENSHOT_ROOT",
    "BrowserLaunchProbe",
    "probe_launch",
    "save_storage_state",
    "screenshot_dir",
    "storage_state_option",
]
