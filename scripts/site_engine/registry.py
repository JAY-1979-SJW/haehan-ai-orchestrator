"""SiteProfileRegistry — site_engine 프로필 등록/조회.

기존 scripts/site_registry.py를 대체하지 않는다.
이 레지스트리는 신규 site_engine 구조에서만 사용된다.
"""

from __future__ import annotations

from scripts.site_engine.profiles import SiteProfile


class SiteProfileRegistry:
    def __init__(self) -> None:
        self._store: dict[str, SiteProfile] = {}

    def register(self, profile: SiteProfile) -> None:
        if not isinstance(profile, SiteProfile):
            raise TypeError(f"Expected SiteProfile, got {type(profile).__name__}")
        if profile.key in self._store:
            raise ValueError(f"Profile already registered: {profile.key!r}")
        self._store[profile.key] = profile

    def get(self, key: str) -> SiteProfile | None:
        return self._store.get(key)

    def get_or_raise(self, key: str) -> SiteProfile:
        profile = self._store.get(key)
        if profile is None:
            raise KeyError(f"No profile registered for key: {key!r}")
        return profile

    def has(self, key: str) -> bool:
        return key in self._store

    def list_profiles(self) -> list[SiteProfile]:
        return list(self._store.values())

    def list_keys(self) -> list[str]:
        return list(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)


_default_registry = SiteProfileRegistry()


def get_default_registry() -> SiteProfileRegistry:
    return _default_registry
