"""사이트 등록표 코어 — 사이트 메타데이터 조회·등록 (사이트별 지식 없음).

결함 #113: 이 파일은 원래 사이트별 로그인 함수 약 12개와 7개 사이트 항목을 직접 품고 있어(L5 사이트 지식) L4 범용 엔진
(cdp_client·login_session·site_access)이 이를 import 하면 층간 위반이었다. 사이트별 지식은 `scripts/site_engine/site_registry_sites.py`(L5)로 옮기고,
이 코어는 `SiteSpec`·조회·등록만 한다. 호출처는 그대로 `get_site`·`list_sites` 를 부른다.

사이트 모듈 연결: 처음 `get_site`/`list_sites` 가 불리면 `_LOADER` 가 가리키는 모듈을 문자열로 불러 `build_sites(SiteSpec)` 결과를 등록한다.
정적 import 가 아니라 **의도적인 데이터 주도(플러그인) 결합**이다 — 런타임에는 코어가 사이트 모듈에 의존하며(결합이 0 은 아님),
달라지는 것은 L4 파일이 사이트 지식을 소유하지 않는다는 점이다. 로더 실패는 삼키지 않고 예외로 알린다(다음 호출에서 다시 시도).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass

_LOADER = "scripts.site_engine.site_registry_sites"  # 변수에 담은 문자열 — 정적 import 가 아니다(위 설명 참고)


@dataclass
class SiteSpec:
    key: str
    base_url: str
    login_domain_hints: tuple[str, ...]  # 로그인 페이지 URL 포함 키워드
    is_logged_in: Callable[[object], bool]  # page → bool
    login: Callable[[object], dict]  # page → {ok, reason, user, needs_manual?}
    login_strategy: str = "registered_only"  # registered_only | registered_then_universal | manual_only


_REGISTRY: dict[str, SiteSpec] = {}
_loaded = False
_loading = False


def register_site(spec: SiteSpec) -> None:
    """사이트를 등록한다. 같은 키가 이미 있으면 거부한다(조용한 덮어쓰기 방지)."""
    if spec.key in _REGISTRY:
        raise ValueError(f"이미 등록된 사이트: {spec.key}")
    _REGISTRY[spec.key] = spec


def _ensure_loaded() -> None:
    """사이트 모듈을 한 번만 불러 등록한다(멱등·재진입 안전). 실패하면 아무것도 등록하지 않고 예외를 올린다."""
    global _loaded, _loading
    if _loaded or _loading:
        return
    _loading = True
    try:
        specs = importlib.import_module(_LOADER).build_sites(SiteSpec)
        for spec in specs:
            register_site(spec)
        _loaded = True
    except BaseException:
        for spec in list(_REGISTRY.values()):  # 일부만 등록된 상태로 남기지 않는다(다음 호출에서 처음부터 다시)
            _REGISTRY.pop(spec.key, None)
        raise
    finally:
        _loading = False


def get_site(key: str) -> SiteSpec | None:
    _ensure_loaded()
    return _REGISTRY.get(key)


def list_sites() -> list[str]:
    _ensure_loaded()
    return list(_REGISTRY.keys())
