"""사이트 등록표 코어 — 사이트 메타데이터 조회·등록 (사이트별 지식 없음).

결함 #113: 이 파일은 원래 사이트별 로그인 함수 약 12개와 7개 사이트 항목을 직접 품고 있어(L5 사이트 지식) L4 범용 엔진
(cdp_client·login_session·site_access)이 이를 import 하면 층간 위반이었다. 사이트별 지식은 `scripts/site_engine/site_registry_sites.py`(L5)로 옮기고,
이 코어는 `SiteSpec`·조회·등록만 한다. 호출처는 그대로 `get_site`·`list_sites` 를 부른다.

사이트 모듈 연결: 이 코어는 사이트 모듈을 import 하지 않는다. 프로세스 진입점이 시작할 때 조합 모듈의 `install()` 이
`configure(provider)` 로 사이트 목록 공급자를 알려 주고, 처음 `get_site`/`list_sites` 가 불릴 때 공급자가 `SiteSpec` 목록을 만든다.
공급자가 없으면(= 진입점이 install 을 빠뜨렸으면) 조용히 빈 목록으로 가지 않고 RuntimeError 로 알린다 — 자동 로그인이 말없이 꺼지지 않게 하기 위해서다.
공급자 실패도 삼키지 않고 예외로 알린다(다음 호출에서 다시 시도).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

@dataclass
class SiteSpec:
    key: str
    base_url: str
    login_domain_hints: tuple[str, ...]  # 로그인 페이지 URL 포함 키워드
    is_logged_in: Callable[[object], bool]  # page → bool
    login: Callable[[object], dict]  # page → {ok, reason, user, needs_manual?}
    login_strategy: str = "registered_only"  # registered_only | registered_then_universal | manual_only


SiteProvider = Callable[[type[SiteSpec]], Iterable[SiteSpec]]  # SiteSpec 클래스를 받아 사이트 목록을 만든다

_REGISTRY: dict[str, SiteSpec] = {}
_provider: SiteProvider | None = None
_loaded = False
_loading = False


def configure(provider: SiteProvider) -> None:
    """사이트 목록 공급자를 알려 준다(진입점 install 용). 같은 공급자를 다시 알려 주면 아무 일도 하지 않는다(멱등)."""
    global _provider, _loaded
    if provider is _provider:
        return
    _provider = provider
    _loaded = False
    _REGISTRY.clear()


def is_configured() -> bool:
    return _provider is not None


def register_site(spec: SiteSpec) -> None:
    """사이트를 등록한다. 같은 키가 이미 있으면 거부한다(조용한 덮어쓰기 방지)."""
    if spec.key in _REGISTRY:
        raise ValueError(f"이미 등록된 사이트: {spec.key}")
    _REGISTRY[spec.key] = spec


def _ensure_loaded() -> None:
    """공급자로 사이트를 한 번만 등록한다(멱등·재진입 안전). 실패하면 아무것도 등록하지 않고 예외를 올린다."""
    global _loaded, _loading
    if _loaded or _loading:
        return
    if _provider is None:
        raise RuntimeError(
            "사이트 등록표가 구성되지 않았습니다 — 진입점이 시작할 때 조합 모듈의 install() 을 불러야 합니다 "
            "(site_registry.configure(provider) 미호출)."
        )
    _loading = True
    try:
        specs = list(_provider(SiteSpec))
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
