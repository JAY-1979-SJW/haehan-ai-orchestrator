"""
Playwright 설치 상태 진단 및 bootstrap 모듈

로컬 에이전트 실행 전 Playwright 환경을 점검한다.
설치 로그에 secret/token/password/cookie 출력 금지.
사용자 브라우저 프로필 삭제 금지.
서버에서 호출하지 않는다 (로컬 PC 전용).
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

# ── 상태 상수 ──────────────────────────────────────────────────────────────────

PLAYWRIGHT_READY = "PLAYWRIGHT_READY"
PLAYWRIGHT_PACKAGE_MISSING = "PLAYWRIGHT_PACKAGE_MISSING"
PLAYWRIGHT_BROWSER_MISSING = "PLAYWRIGHT_BROWSER_MISSING"
PLAYWRIGHT_INSTALL_REQUIRED = "PLAYWRIGHT_INSTALL_REQUIRED"
PLAYWRIGHT_INSTALL_FAILED = "PLAYWRIGHT_INSTALL_FAILED"
PLAYWRIGHT_LAUNCH_FAILED = "PLAYWRIGHT_LAUNCH_FAILED"
NETWORK_BLOCKED = "NETWORK_BLOCKED"
PERMISSION_DENIED = "PERMISSION_DENIED"
UNKNOWN_ERROR = "UNKNOWN_ERROR"

_ALL_STATES: frozenset[str] = frozenset(
    {
        PLAYWRIGHT_READY,
        PLAYWRIGHT_PACKAGE_MISSING,
        PLAYWRIGHT_BROWSER_MISSING,
        PLAYWRIGHT_INSTALL_REQUIRED,
        PLAYWRIGHT_INSTALL_FAILED,
        PLAYWRIGHT_LAUNCH_FAILED,
        NETWORK_BLOCKED,
        PERMISSION_DENIED,
        UNKNOWN_ERROR,
    }
)

# ── headed/headless 정책 상수 ──────────────────────────────────────────────────

BROWSER_POLICY = {
    "headless_default": True,
    "headed_on_user_auth_required": True,
    "bring_to_front_on_auth_required": True,
    "close_browser_after_task": False,
    "keep_local_profile": True,
}


def check_playwright_status() -> dict[str, Any]:
    """
    Playwright 설치 상태를 진단하고 결과를 반환한다.

    반환:
      status: PLAYWRIGHT_READY 등 상태 상수
      package_version: 버전 문자열 (없으면 None)
      browser_available: bool
      install_command: 설치 필요 시 안내 명령 (없으면 None)
      message_ko: 사용자 안내 문구
    """
    # 1. 패키지 확인
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        version = _get_playwright_version()
    except ImportError:
        return _result(
            PLAYWRIGHT_PACKAGE_MISSING,
            package_version=None,
            browser_available=False,
            install_command="pip install playwright",
            message_ko=("playwright Python 패키지가 설치되어 있지 않습니다.\n설치 명령: pip install playwright"),
        )

    # 2. Chromium binary 확인 (about:blank 실행)
    launch_ok, launch_error = _try_launch_chromium()
    if launch_ok:
        return _result(
            PLAYWRIGHT_READY,
            package_version=version,
            browser_available=True,
            install_command=None,
            message_ko=f"Playwright {version} 준비 완료. Chromium 사용 가능.",
        )

    # launch 실패 원인 분류
    return _classify_launch_error(launch_error, version)


def install_chromium() -> dict[str, Any]:
    """
    Chromium 브라우저 바이너리를 설치한다.
    네트워크/권한 오류는 WARN으로 분류하고 사용자에게 안내한다.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
        )
        if result.returncode == 0:
            # 재진단
            return check_playwright_status()

        stderr = result.stderr[:500] if result.stderr else ""
        if "permission" in stderr.lower() or "access" in stderr.lower():
            return _result(
                PERMISSION_DENIED,
                package_version=_get_playwright_version(),
                browser_available=False,
                install_command="python -m playwright install chromium",
                message_ko=(
                    "Chromium 설치 권한이 없습니다.\n"
                    "관리자 권한으로 실행하거나 직접 설치해 주세요:\n"
                    "python -m playwright install chromium"
                ),
            )
        if "network" in stderr.lower() or "connect" in stderr.lower() or "timeout" in stderr.lower():
            return _result(
                NETWORK_BLOCKED,
                package_version=_get_playwright_version(),
                browser_available=False,
                install_command="python -m playwright install chromium",
                message_ko=(
                    "네트워크 오류로 Chromium 설치에 실패했습니다.\n"
                    "인터넷 연결을 확인하고 다시 시도해 주세요:\n"
                    "python -m playwright install chromium"
                ),
            )
        return _result(
            PLAYWRIGHT_INSTALL_FAILED,
            package_version=_get_playwright_version(),
            browser_available=False,
            install_command="python -m playwright install chromium",
            message_ko=(
                f"Chromium 설치에 실패했습니다.\n"
                f"직접 실행해 주세요: python -m playwright install chromium\n"
                f"오류: {stderr[:200]}"
            ),
        )
    except subprocess.TimeoutExpired:
        return _result(
            PLAYWRIGHT_INSTALL_FAILED,
            package_version=_get_playwright_version(),
            browser_available=False,
            install_command="python -m playwright install chromium",
            message_ko="Chromium 설치 시간이 초과되었습니다. 네트워크 상태를 확인해 주세요.",
        )
    except Exception as exc:  # noqa: BLE001 - Playwright 설치상태 진단/설치 유틸(로컬 PC 전용, 문서에 '설치 로그에 secret 출력 금지' 명시) — 버전조회/브라우저실행테스트/설치 실패 시 모두 상태 코드(UNKNOWN_ERROR 등)와 함께 명확히 실패로 보고됨.
        return _result(
            UNKNOWN_ERROR,
            package_version=_get_playwright_version(),
            browser_available=False,
            install_command="python -m playwright install chromium",
            message_ko=f"알 수 없는 오류: {type(exc).__name__}: {str(exc)[:100]}",
        )


def ensure_playwright_ready(auto_install: bool = False) -> dict[str, Any]:
    """
    Playwright 준비 상태를 보장한다.
    auto_install=True이면 browser binary 누락 시 자동 설치를 시도한다.
    """
    status = check_playwright_status()
    if status["status"] == PLAYWRIGHT_READY:
        return status

    if auto_install and status["status"] in (PLAYWRIGHT_BROWSER_MISSING, PLAYWRIGHT_INSTALL_REQUIRED):
        return install_chromium()

    return status


def get_launch_options(requires_user_auth: bool = False) -> dict[str, Any]:
    """
    headed/headless 실행 옵션을 반환한다.

    requires_user_auth=True이면 headed 모드로 브라우저를 앞으로 표시한다.
    인증 필요 상태에서 headless로 계속 진행하지 않는다.
    """
    if requires_user_auth:
        return {
            "headless": False,
            "bring_to_front": True,
            "reason": "사용자 인증이 필요합니다. 브라우저를 앞으로 표시합니다.",
        }
    return {
        "headless": BROWSER_POLICY["headless_default"],
        "bring_to_front": False,
        "reason": "일반 조회. headless 실행.",
    }


def _try_launch_chromium() -> tuple[bool, str]:
    """Chromium을 about:blank로 실행해 본다. 성공 여부와 오류 메시지 반환."""
    probe = r"""
from __future__ import annotations

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("about:blank", timeout=10000)
        browser.close()
    print("PLAYWRIGHT_LAUNCH_OK")
except Exception as exc:
    message = str(exc).replace("\r", " ").replace("\n", " ")
    print(f"PLAYWRIGHT_LAUNCH_ERROR:{type(exc).__name__}:{message[:1000]}")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - Playwright 설치상태 진단/설치 유틸(로컬 PC 전용, 문서에 '설치 로그에 secret 출력 금지' 명시) — 버전조회/브라우저실행테스트/설치 실패 시 모두 상태 코드(UNKNOWN_ERROR 등)와 함께 명확히 실패로 보고됨.
        return False, str(exc)
    if "PLAYWRIGHT_LAUNCH_OK" in result.stdout:
        return True, ""
    marker = next(
        (line for line in result.stdout.splitlines() if line.startswith("PLAYWRIGHT_LAUNCH_ERROR:")),
        "",
    )
    if marker:
        return False, marker.removeprefix("PLAYWRIGHT_LAUNCH_ERROR:")
    combined = (result.stdout + "\n" + result.stderr).strip()
    return False, combined[:1000] or f"exit_code={result.returncode}"


def _classify_launch_error(error: str, version: str | None) -> dict[str, Any]:
    """launch 실패 원인을 분류한다."""
    lower = error.lower()
    if "executable" in lower or "not found" in lower or "browser" in lower:
        return _result(
            PLAYWRIGHT_BROWSER_MISSING,
            package_version=version,
            browser_available=False,
            install_command="python -m playwright install chromium",
            message_ko=("Chromium 바이너리가 없습니다.\n설치 명령: python -m playwright install chromium"),
        )
    if "permission" in lower or "access denied" in lower:
        return _result(
            PERMISSION_DENIED,
            package_version=version,
            browser_available=False,
            install_command="python -m playwright install chromium",
            message_ko="권한 오류. 관리자 권한으로 실행해 주세요.",
        )
    return _result(
        PLAYWRIGHT_LAUNCH_FAILED,
        package_version=version,
        browser_available=False,
        install_command="python -m playwright install chromium",
        message_ko=f"브라우저 실행 실패: {error[:200]}",
    )


def _get_playwright_version() -> str | None:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        return result.stdout.strip().replace("Version ", "") if result.returncode == 0 else None
    except Exception:  # noqa: BLE001 - Playwright 설치상태 진단/설치 유틸(로컬 PC 전용, 문서에 '설치 로그에 secret 출력 금지' 명시) — 버전조회/브라우저실행테스트/설치 실패 시 모두 상태 코드(UNKNOWN_ERROR 등)와 함께 명확히 실패로 보고됨.
        return None


def _result(
    status: str,
    package_version: str | None,
    browser_available: bool,
    install_command: str | None,
    message_ko: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "package_version": package_version,
        "browser_available": browser_available,
        "install_command": install_command,
        "message_ko": message_ko,
        "browser_policy": dict(BROWSER_POLICY),
    }
