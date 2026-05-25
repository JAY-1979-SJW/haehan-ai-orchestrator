"""HaehanAI Admin Mode pywebview lazy load (HAEHAN_ADMIN_MODE_WEBVIEW_LAZY_LOAD_01).

Admin Mode = role admin/owner 사용자만 접근 가능한 풀 React UI.
pywebview 는 모듈 import 시점에 import 하지 않고 open_admin_window 호출 시점에만 lazy import.

원칙:
  1. 모듈 import 시 pywebview/webview import 금지 (top-level import 금지)
  2. HAEHAN_SKIP_GUI=1 환경에서는 실제 창 생성 금지
  3. role admin/owner 만 진입 가능
  4. 127.0.0.1/localhost 이라는 이유로 role 검사 우회 금지 (local-only bypass forbidden)
  5. whoami 응답에 token / device_token / registration_code / secret 키 발견 시 거부
  6. 같은 프로세스 내 admin window 중복 생성 방지
  7. 창 닫기는 local_server 종료시키지 않음 (open_admin_window 반환만 함)

Legacy webview entrypoints are removed; Desktop.exe enters through main_launcher.
본 모듈은 통합 HaehanAI.exe 의 Admin Mode 전용.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

# NOTE: pywebview / webview 는 절대로 본 모듈 top-level 에 import 하지 말 것.
# open_admin_window() 내부에서만 lazy import 한다.
# AST 기반 audit 가 top-level import 를 차단함.

logger = logging.getLogger(__name__)

ADMIN_ROLES = frozenset({"admin", "owner"})
KNOWN_ROLES = frozenset({"any", "user", "viewer", "admin", "owner"})

# whoami 응답에 등장하면 안 되는 키 (substring 매칭).
_FORBIDDEN_RESPONSE_KEYS = frozenset({
    "token", "device_token", "registration_code", "secret",
    "bearer", "api_key", "password", "session", "cookie",
    "sk-", "sk_",
})


# ── role 판단 ──────────────────────────────────────────────────────────

def is_admin_role(role: str) -> bool:
    """role 이 admin/owner 인지 — 순수 함수."""
    return (role or "").strip().lower() in ADMIN_ROLES


@dataclass
class RoleGuardResult:
    """role 검사 결과 — token/secret 절대 미포함."""
    passed: bool
    role: str
    source: str  # "explicit" / "api" / "default"
    reason: str = ""


def _detect_response_secrets(data: dict) -> list[str]:
    """응답 dict 에 secret 의심 키가 있는지."""
    out: list[str] = []
    for k in data.keys():
        kl = str(k or "").lower()
        for fk in _FORBIDDEN_RESPONSE_KEYS:
            if fk in kl:
                out.append(str(k))
                break
    return out


def _default_api_caller(server_url: str, timeout: float) -> dict:
    """기본 /api/v1/whoami 호출. 응답 dict 반환."""
    import json as _json
    import urllib.request as _urlreq
    url = server_url.rstrip("/") + "/api/v1/whoami"
    with _urlreq.urlopen(url, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    data = _json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("whoami_invalid_response")
    return data


def check_role_via_api(
    *,
    server_url: str = "http://127.0.0.1:8765",
    timeout: float = 3.0,
    explicit_role: Optional[str] = None,
    api_caller: Optional[Callable[[str, float], dict]] = None,
) -> RoleGuardResult:
    """role 검사 — 127.0.0.1 이라도 admin/owner 만 통과.

    explicit_role 주입 시 (테스트/CLI): 그 role 로 검사 (api 호출 X)
    api_caller 주입 시 (테스트): 그 함수로 whoami 호출
    """
    # explicit role 우선 — local-only bypass 가 아님 (테스트/CLI 명시 입력 처리)
    if explicit_role is not None:
        role = (explicit_role or "").strip().lower()
        passed = is_admin_role(role)
        return RoleGuardResult(
            passed=passed, role=role, source="explicit",
            reason="" if passed else f"insufficient_role:{role or 'empty'}",
        )

    caller = api_caller or _default_api_caller

    try:
        data = caller(server_url, timeout)
    except Exception as e:
        return RoleGuardResult(
            passed=False, role="", source="api",
            reason=f"api_error:{type(e).__name__}",
        )

    # secret leak 검사 — 응답에 금지 키가 있으면 거부
    leaks = _detect_response_secrets(data)
    if leaks:
        logger.warning("whoami response contains forbidden keys: %s", leaks)
        return RoleGuardResult(
            passed=False, role="", source="api",
            reason="whoami_response_contains_secret_keys",
        )

    role = str(data.get("role") or "").strip().lower()
    passed = is_admin_role(role)
    return RoleGuardResult(
        passed=passed, role=role, source="api",
        reason="" if passed else f"insufficient_role:{role or 'empty'}",
    )


def resolve_current_role(
    *,
    server_url: str = "http://127.0.0.1:8765",
    explicit_role: Optional[str] = None,
    api_caller: Optional[Callable[[str, float], dict]] = None,
    api_timeout: float = 1.5,
) -> str:
    """현재 사용자 role 결정 — explicit > env HAEHAN_ROLE > api > 'any'."""
    if explicit_role is not None:
        r = (explicit_role or "").strip().lower()
        return r if r in KNOWN_ROLES else "any"

    env_role = os.environ.get("HAEHAN_ROLE", "").strip().lower()
    if env_role in KNOWN_ROLES:
        return env_role

    try:
        guard = check_role_via_api(
            server_url=server_url,
            timeout=api_timeout,
            api_caller=api_caller,
        )
        if guard.role and guard.role in KNOWN_ROLES:
            return guard.role
    except Exception:
        pass

    return "any"


# ── single instance lock ─────────────────────────────────────────────────

_admin_window_lock = threading.Lock()
_admin_window_active = False


def is_admin_window_active() -> bool:
    """현재 admin window 가 활성인지 — 외부 조회용."""
    return _admin_window_active


def _try_acquire_window() -> bool:
    """창 슬롯 획득 시도. 이미 활성이면 False."""
    global _admin_window_active
    with _admin_window_lock:
        if _admin_window_active:
            return False
        _admin_window_active = True
        return True


def _release_window() -> None:
    global _admin_window_active
    with _admin_window_lock:
        _admin_window_active = False


def _reset_admin_window_state() -> None:
    """테스트 전용 — 강제 리셋."""
    _release_window()


def _is_skip_gui() -> bool:
    """HAEHAN_SKIP_GUI 환경변수 평가."""
    return os.environ.get("HAEHAN_SKIP_GUI", "").strip() in ("1", "true", "True")


# ── 진입점 ─────────────────────────────────────────────────────────────

def open_admin_window(
    *,
    explicit_role: Optional[str] = None,
    server_url: str = "http://127.0.0.1:8765",
    title: str = "HaehanAI Admin",
    width: int = 1200,
    height: int = 800,
    api_caller: Optional[Callable[[str, float], dict]] = None,
    skip_gui: Optional[bool] = None,
    webview_starter: Optional[Callable[..., None]] = None,
    webview_creator: Optional[Callable[..., Any]] = None,
) -> dict:
    """Admin Mode pywebview 창 열기.

    Returns:
        {
          "ok": bool,
          "reason": str,         # 성공/실패 이유
          "role": str,           # 검사된 role
          "window_opened": bool, # 실제 창 생성 여부
          "skip_gui": bool,
        }

    창 닫기 = 본 함수 반환. local_server 는 종료시키지 않음 — 호출자 책임 (lifecycle).
    """
    if skip_gui is None:
        skip_gui = _is_skip_gui()

    # 1) role guard
    guard = check_role_via_api(
        server_url=server_url,
        explicit_role=explicit_role,
        api_caller=api_caller,
    )

    if not guard.passed:
        logger.warning("Admin role guard failed: %s (role=%s, source=%s)",
                       guard.reason, guard.role, guard.source)
        return {
            "ok": False,
            "reason": guard.reason or "role_guard_failed",
            "role": guard.role,
            "window_opened": False,
            "skip_gui": skip_gui,
        }

    # 2) single instance
    if not _try_acquire_window():
        logger.info("Admin window already open — skip")
        return {
            "ok": True,
            "reason": "already_open",
            "role": guard.role,
            "window_opened": False,
            "skip_gui": skip_gui,
        }

    # 3) skip_gui — 실제 창 생성 안 함
    if skip_gui:
        _release_window()
        return {
            "ok": True,
            "reason": "skip_gui_no_window",
            "role": guard.role,
            "window_opened": False,
            "skip_gui": True,
        }

    # 4) lazy import pywebview — 본 라인 이전에 webview 가 import 되어 있으면 안 됨
    try:
        import webview as _webview  # type: ignore  # noqa: PLC0415
    except Exception as e:
        _release_window()
        logger.error("pywebview import 실패: %s", type(e).__name__)
        return {
            "ok": False,
            "reason": f"pywebview_unavailable:{type(e).__name__}",
            "role": guard.role,
            "window_opened": False,
            "skip_gui": False,
        }

    try:
        creator = webview_creator or _webview.create_window
        creator(
            title, server_url,
            width=width, height=height,
            min_size=(800, 560), resizable=True,
        )
        starter = webview_starter or _webview.start
        starter(debug=False)
        # webview.start 는 모든 창이 닫힐 때까지 블로킹
        return {
            "ok": True,
            "reason": "window_closed",
            "role": guard.role,
            "window_opened": True,
            "skip_gui": False,
        }
    except Exception as e:
        logger.error("admin webview 실행 오류: %s", type(e).__name__)
        return {
            "ok": False,
            "reason": f"webview_error:{type(e).__name__}",
            "role": guard.role,
            "window_opened": False,
            "skip_gui": False,
        }
    finally:
        _release_window()


def run_admin_mode_full(
    *,
    explicit_role: Optional[str] = None,
    server_url: str = "http://127.0.0.1:8765",
    api_caller: Optional[Callable[[str, float], dict]] = None,
    skip_gui: Optional[bool] = None,
) -> dict:
    """main_launcher.run_admin_mode() 통합 진입 — open_admin_window 래퍼."""
    return open_admin_window(
        explicit_role=explicit_role,
        server_url=server_url,
        api_caller=api_caller,
        skip_gui=skip_gui,
    )


__all__ = [
    "ADMIN_ROLES", "KNOWN_ROLES",
    "RoleGuardResult",
    "is_admin_role", "check_role_via_api", "resolve_current_role",
    "open_admin_window", "run_admin_mode_full",
    "is_admin_window_active",
]
