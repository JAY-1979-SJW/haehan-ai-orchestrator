"""F-4C — Trusted Browser Automation policy gateway.

본 모듈은 trusted browser automation 트랙의 **요청 검증 게이트웨이** 다.
모든 trusted automation 호출은 진입 시 다음을 통과해야 한다:

  1) 대상 host 가 ``ALLOWED_TRUSTED_SITES`` 의 정확 매칭 또는 서브도메인.
  2) action 이름이 ``BLOCKED_TRUSTED_ACTIONS`` 에 없음.
  3) 파라미터에 raw 비밀값 (password/cookie/session 등) 이 없음.
  4) 다운로드 대상 폴더가 ``allowed_download_roots`` 안에 있음.

본 모듈은 **검증/분류만** 한다. 실제 브라우저 launch / 클릭은 본 단계에
포함되지 않는다.

Google/YouTube open-only 정책 (F-2) 과 충돌 금지:
  - 본 모듈은 hometax 같은 별도 trusted host 만 허용한다.
  - Google / YouTube 도메인은 ``ALLOWED_TRUSTED_SITES`` 에 들어있지 않
    으므로 본 모듈로 trusted automation 진입이 거절된다 (open-only 유지).
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Mapping, Optional, Tuple
from urllib.parse import urlparse

from . import trusted_secrets


# ─── 정책 상수 ────────────────────────────────────────────────────────────

# 허용 host (정확 일치 또는 서브도메인). lowercase.
ALLOWED_TRUSTED_SITES: Tuple[str, ...] = (
    "hometax.go.kr",
    "www.hometax.go.kr",
)

# trusted automation 안에서 허용되는 상위 action 이름.
ALLOWED_TRUSTED_ACTIONS: Tuple[str, ...] = (
    "trusted_login",
    "observe_authenticated_page",
    "navigate_readonly",
    "download_file",
    "save_result",
)

# 절대 자동화하지 않는 action.
BLOCKED_TRUSTED_ACTIONS: Tuple[str, ...] = (
    "submit_tax_return",
    "pay_tax",
    "issue_tax_invoice",
    "change_business_info",
    "delegate_permission_change",
    "captcha_bypass",
    "export_cookie",
    "export_session",
    "export_storage",
    "read_saved_password",
)

# 사용자가 직접 화면을 봐야 하는 상황.
#
# 보안프로그램 군 (security_program_required / keyboard_security_required /
# certificate_plugin_required / browser_not_supported /
# manual_install_required) 은 자동 설치/silent install/관리자 권한 실행/
# 보안모듈 우회 어떤 것도 수행하지 않는다. 사용자가 직접 설치/승인 후
# 재시도하는 흐름이며, 본 정책은 trusted automation 자동 진입을 차단한다.
REQUIRES_USER_PRESENCE: Tuple[str, ...] = (
    "first_login_setup",
    "ambiguous_certificate_selection",
    "mobile_2fa_push",
    "captcha_or_bot_check",
    "payment_or_submission_confirmation",
    "security_program_required",
    "keyboard_security_required",
    "certificate_plugin_required",
    "browser_not_supported",
    "manual_install_required",
)

# 다운로드 대상 폴더 prefix 의 시스템 영역 차단 리스트 (lowercase).
_BLOCKED_DOWNLOAD_PREFIXES: Tuple[str, ...] = (
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata",
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/var",
    "/boot",
)


# ─── 외부 API ────────────────────────────────────────────────────────────

def is_allowed_trusted_site(url_or_host: str) -> bool:
    """대상 URL 또는 host 문자열이 trusted automation 허용 호스트인지.

    정확 일치 또는 서브도메인 (``host.endswith("." + d)``) 만 허용.
    그 외 (스키마 잘못/host 비어있음/none) 은 모두 False.
    """
    host = _extract_host(url_or_host)
    if not host:
        return False
    for allowed in ALLOWED_TRUSTED_SITES:
        if host == allowed:
            return True
        if host.endswith("." + allowed):
            return True
    return False


def is_blocked_trusted_action(action_name: Any) -> bool:
    """action 이름이 차단 목록에 있으면 True."""
    if not isinstance(action_name, str):
        return False
    return action_name.strip().lower() in BLOCKED_TRUSTED_ACTIONS


def is_allowed_trusted_action(action_name: Any) -> bool:
    """action 이름이 허용 목록에 있으면 True."""
    if not isinstance(action_name, str):
        return False
    return action_name.strip().lower() in ALLOWED_TRUSTED_ACTIONS


def validate_trusted_automation_request(
    params: Any,
    *,
    allowed_download_roots: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """trusted automation 한 호출의 종합 검증.

    필수 파라미터:
      site_key:       lowercase 사이트 키 (registry 검증과 별도)
      target_url:     ``http(s)://...`` 형식, host 가 allowlist 안
      action:         ALLOWED_TRUSTED_ACTIONS 안

    선택 파라미터:
      secret_ref:     SecretRef dict — 있으면 ``trusted_secrets`` 가 검증
      download_path:  ``download_file`` action 일 때 필수, allowlist 안

    반환:
      {"ok": bool, "error_code": str, "warnings": [str, ...]}
    """
    if not isinstance(params, Mapping):
        return _err("PARAMS_NOT_MAPPING")

    raw_check = trusted_secrets.reject_raw_secret_params(params)
    if not raw_check["ok"]:
        return raw_check

    action = params.get("action")
    if is_blocked_trusted_action(action):
        return _err("ACTION_BLOCKED", f"blocked_action:{str(action).lower()}")
    if not is_allowed_trusted_action(action):
        return _err("ACTION_NOT_ALLOWED")

    target_url = params.get("target_url") or ""
    if not isinstance(target_url, str) or not target_url.strip():
        return _err("MISSING_TARGET_URL")
    if not is_allowed_trusted_site(target_url):
        return _err("HOST_NOT_ALLOWED")

    secret_ref = params.get("secret_ref")
    if secret_ref is not None:
        ref_check = trusted_secrets.validate_secret_ref(secret_ref)
        if not ref_check["ok"]:
            return ref_check

    if str(action).strip().lower() == "download_file":
        download_path = params.get("download_path") or ""
        path_check = _validate_download_path(
            download_path,
            allowed_roots=allowed_download_roots,
        )
        if not path_check["ok"]:
            return path_check

    return {"ok": True, "error_code": "", "warnings": []}


def sanitize_trusted_result(data: Any) -> Any:
    """ActionResult/audit 로 보내기 전 결과 dict 를 마스킹.

    - raw 비밀값 키는 ``"***"`` 로 치환.
    - ``*_secret_id`` 는 prefix 만 노출.
    - 나머지는 그대로.
    """
    return trusted_secrets.redact_for_log(data)


# ─── 내부 ─────────────────────────────────────────────────────────────────

def _extract_host(url_or_host: Any) -> str:
    if not isinstance(url_or_host, str):
        return ""
    s = url_or_host.strip()
    if not s:
        return ""
    # url 형식이면 hostname 만, 아니면 그 자체를 lowercase host 로 본다.
    if "://" in s:
        try:
            parsed = urlparse(s)
        except Exception:  # noqa: BLE001
            return ""
        # http(s) 외 스킴은 trusted automation 진입을 거절.
        if (parsed.scheme or "").lower() not in ("http", "https"):
            return ""
        return (parsed.hostname or "").lower()
    # host 문자열만 들어온 경우.
    if "/" in s or " " in s:
        return ""
    return s.lower()


def _validate_download_path(
    path: str,
    *,
    allowed_roots: Optional[Iterable[str]],
) -> dict[str, Any]:
    if not isinstance(path, str) or not path.strip():
        return _err("MISSING_DOWNLOAD_PATH")
    norm = os.path.normpath(path).strip()
    norm_lower = norm.lower()

    for blocked in _BLOCKED_DOWNLOAD_PREFIXES:
        if norm_lower.startswith(blocked):
            return _err("DOWNLOAD_PATH_BLOCKED")

    if allowed_roots is None:
        return _err("DOWNLOAD_ROOTS_NOT_CONFIGURED")

    roots = [os.path.normpath(r).lower() for r in allowed_roots if r]
    if not roots:
        return _err("DOWNLOAD_ROOTS_EMPTY")

    for root in roots:
        if norm_lower == root or norm_lower.startswith(root + os.sep.lower()):
            return {"ok": True, "error_code": "", "warnings": []}
        # 슬래시 정규화 차이 보호 (Windows ``\\`` vs ``/``).
        alt_sep = "/" if os.sep == "\\" else "\\"
        if norm_lower.startswith(root + alt_sep):
            return {"ok": True, "error_code": "", "warnings": []}

    return _err("DOWNLOAD_PATH_NOT_IN_ALLOWED_ROOTS")


def _err(code: str, *warnings: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "warnings": [code.lower(), *warnings],
    }


__all__ = [
    "ALLOWED_TRUSTED_SITES",
    "ALLOWED_TRUSTED_ACTIONS",
    "BLOCKED_TRUSTED_ACTIONS",
    "REQUIRES_USER_PRESENCE",
    "is_allowed_trusted_site",
    "is_allowed_trusted_action",
    "is_blocked_trusted_action",
    "validate_trusted_automation_request",
    "sanitize_trusted_result",
]
