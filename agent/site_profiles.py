"""사이트별 로그인 프로필 레지스트리.

원칙
- **임의 사이트 자동 추론 금지.** 프로필이 명시적으로 등록된 site_key 만
  ``login_with_secret`` 의 대상이 될 수 있다.
- selector / allowed_hosts 는 하드코딩이 아닌 "명시적 설정" 구조로 노출된다.
- 이번 단계에서는 구조 정의가 목적이므로 기본 레지스트리는 비어 있다.
  실제 사이트 프로필은 각 로컬 PC 에서 ``register_profile(...)`` 로
  등록하거나, 별도 부트스트랩 모듈에서 한 번만 등록한다.

SuccessCheck.kind 의미
- ``url``      : 로그인 후 page.url 에 value 문자열이 포함되면 성공으로 간주
- ``selector`` : 로그인 후 해당 CSS selector 요소가 1개 이상 존재하면 성공
- ``text``     : 로그인 후 body 텍스트에 value 문자열이 포함되면 성공
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

SUCCESS_KINDS: frozenset[str] = frozenset({"url", "selector", "text"})


@dataclass(frozen=True)
class SuccessCheck:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in SUCCESS_KINDS:
            raise ValueError(
                f"invalid success_check.kind: {self.kind!r} "
                f"(must be one of {sorted(SUCCESS_KINDS)})"
            )
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("success_check.value must be a non-empty string")


@dataclass(frozen=True)
class SiteProfile:
    site_key: str
    login_url: str
    username_selector: str
    password_selector: str
    submit_selector: str
    success_check: SuccessCheck
    allowed_hosts: tuple[str, ...]
    # 로그인 후 탐색 가능한 path prefix 목록. 비어 있으면 path 제한 없음.
    # 임의 외부 페이지 이동을 막기 위해 명시적으로 제한 권장.
    post_login_allowed_paths: tuple[str, ...] = ()
    # (선택) target_url 도달 이후 추가 success 검증
    inspect_success_check: Optional[SuccessCheck] = None

    def __post_init__(self) -> None:
        for name in (
            "site_key",
            "login_url",
            "username_selector",
            "password_selector",
            "submit_selector",
        ):
            v = getattr(self, name)
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.allowed_hosts, tuple) or not self.allowed_hosts:
            raise ValueError("allowed_hosts must be a non-empty tuple of hostnames")
        if not isinstance(self.post_login_allowed_paths, tuple):
            raise ValueError("post_login_allowed_paths must be a tuple")
        for p in self.post_login_allowed_paths:
            if not isinstance(p, str) or not p.startswith("/"):
                raise ValueError(
                    "each post_login_allowed_paths entry must start with '/'"
                )
        if self.inspect_success_check is not None and not isinstance(
            self.inspect_success_check, SuccessCheck
        ):
            raise ValueError("inspect_success_check must be SuccessCheck or None")


# 레지스트리는 _비어 있는_ 상태로 시작한다. 임의 사이트는 자동 등록되지 않는다.
_REGISTRY: dict[str, SiteProfile] = {}


def register_profile(profile: SiteProfile) -> None:
    """프로필을 레지스트리에 등록 또는 덮어쓰기."""
    if not isinstance(profile, SiteProfile):
        raise TypeError("profile must be a SiteProfile")
    _REGISTRY[profile.site_key] = profile


def unregister_profile(site_key: str) -> bool:
    return _REGISTRY.pop(site_key, None) is not None


def get_profile(site_key: str) -> Optional[SiteProfile]:
    if not isinstance(site_key, str):
        return None
    return _REGISTRY.get(site_key)


def list_profiles() -> list[str]:
    return sorted(_REGISTRY.keys())


def is_target_path_allowed(profile: SiteProfile, url: str) -> bool:
    """``url`` 의 path 가 profile.post_login_allowed_paths 중 하나로 시작하는지.

    ``post_login_allowed_paths`` 가 비어 있으면 path 제한 없음(True).
    지정되어 있으면 접두사 일치 중 하나라도 있어야 True.
    """
    if not profile.post_login_allowed_paths:
        return True
    if not isinstance(url, str) or not url:
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    path = p.path or "/"
    for prefix in profile.post_login_allowed_paths:
        if isinstance(prefix, str) and prefix and path.startswith(prefix):
            return True
    return False


def is_host_allowed(profile: SiteProfile, url: str) -> bool:
    """``url`` 의 host 가 profile.allowed_hosts 중 하나와 매칭되는지.

    정확 일치 또는 "*.allowed_host" 서브도메인 일치만 허용한다.
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    for raw in profile.allowed_hosts:
        if not isinstance(raw, str):
            continue
        h = raw.strip().lower()
        if not h:
            continue
        if host == h or host.endswith("." + h):
            return True
    return False


__all__ = [
    "SUCCESS_KINDS",
    "SuccessCheck",
    "SiteProfile",
    "register_profile",
    "unregister_profile",
    "get_profile",
    "list_profiles",
    "is_host_allowed",
    "is_target_path_allowed",
]
