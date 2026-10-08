"""Browser Site Registry — site_id 기반 사이트 정책 (raw URL 직접 실행 차단).

LOCAL_BROWSER_POLICY_SAFE_EXPANSION_A1 STEP 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

EXECUTION_LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
EXECUTION_SERVER_FORBIDDEN = "SERVER_FORBIDDEN"

LOGIN_USER_PRESENT_ONLY = "USER_PRESENT_ONLY"
LOGIN_PUBLIC_READONLY = "PUBLIC_READONLY"
LOGIN_USER_PRESENT_AFTER_LOGIN = "USER_PRESENT_AFTER_LOGIN"

CRED_NO_CAPTURE = "NO_CREDENTIAL_CAPTURE"
CAPTURE_NONE = "NO_SCREENSHOT_NO_HAR"

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


@dataclass(frozen=True)
class SitePolicy:
    site_id: str
    label: str
    allowed_hosts: tuple[str, ...]
    allowed_paths: tuple[str, ...] = ()
    blocked_paths: tuple[str, ...] = ()
    allowed_purposes: tuple[str, ...] = ()
    execution_location: str = EXECUTION_LOCAL_AGENT_REQUIRED
    login_mode: str = LOGIN_PUBLIC_READONLY
    credential_policy: str = CRED_NO_CAPTURE
    capture_policy: str = CAPTURE_NONE
    allowed_actions: tuple[str, ...] = ()
    blocked_actions: tuple[str, ...] = (
        "submit",
        "save",
        "sign",
        "delete",
        "payment",
        "bid",
        "transfer",
    )
    risk_level: str = RISK_MEDIUM
    requires_approval: bool = True
    notes: str = ""


_REGISTRY: dict[str, SitePolicy] = {}


def register_site(policy: SitePolicy) -> None:
    if not policy.site_id:
        raise ValueError("site_id 필수")
    if not policy.allowed_hosts:
        raise ValueError("allowed_hosts 비어 있음 — 차단")
    if policy.execution_location == "SERVER":
        raise ValueError("서버 실행 금지")
    _REGISTRY[policy.site_id] = policy


def get_site(site_id: str) -> SitePolicy | None:
    return _REGISTRY.get(site_id)


def list_sites() -> list[str]:
    return sorted(_REGISTRY.keys())


def clear_all() -> None:
    _REGISTRY.clear()


def resolve_url(site_id: str, path_key: str = "/", query_safe: dict | None = None) -> dict[str, Any]:
    """site_id + path_key를 통해서만 URL 생성. raw URL 직접 실행 차단."""
    policy = get_site(site_id)
    if policy is None:
        return {"ok": False, "verdict": "UNKNOWN_SITE", "error": f"site_id 미등록: {site_id}"}
    if policy.allowed_paths and path_key not in policy.allowed_paths:
        return {"ok": False, "verdict": "PATH_NOT_ALLOWED", "error": path_key}
    if path_key in policy.blocked_paths:
        return {"ok": False, "verdict": "PATH_BLOCKED", "error": path_key}
    host = policy.allowed_hosts[0]
    return {
        "ok": True,
        "verdict": "URL_RESOLVED",
        "site_id": site_id,
        "host": host,
        "path_key": path_key,
        "execution_location": policy.execution_location,
        "login_mode": policy.login_mode,
    }


def validate_raw_url(raw_url: str) -> dict[str, Any]:
    """raw URL 직접 실행 시도 검증 — 등록된 site_id로만 허용."""
    if not raw_url:
        return {"ok": False, "verdict": "EMPTY_URL"}
    try:
        parsed = urlparse(raw_url)
    except Exception:  # noqa: BLE001 - URL 파싱 실패 시 {ok: False, verdict: URL_PARSE_ERROR} 반환 — fail-closed, 허용되지 않은 것으로 처리
        return {"ok": False, "verdict": "URL_PARSE_ERROR"}
    host = (parsed.hostname or "").lower()
    if not host:
        return {"ok": False, "verdict": "RAW_URL_BLOCKED", "error": "host 없음"}
    for policy in _REGISTRY.values():
        if host in policy.allowed_hosts:
            return {
                "ok": True,
                "verdict": "ALLOWED_VIA_REGISTRY",
                "site_id": policy.site_id,
                "host": host,
            }
    return {"ok": False, "verdict": "RAW_URL_BLOCKED", "error": f"등록되지 않은 host: {host}"}
