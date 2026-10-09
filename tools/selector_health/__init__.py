"""셀렉터 헬스체크 패키지.

사용:
    python tools/selector_health/selector_health_check.py naver_blog
    python tools/selector_health/selector_health_check.py --all
"""

from __future__ import annotations

from tools.selector_health.core import (  # noqa: F401
    ERROR,
    HIDDEN,
    MISSING,
    OK,
    SKIPPED,
    CheckResult,
    SelectorCheck,
    SiteSpec,
    format_report,
    run_site_checks,
)


def load_specs() -> dict[str, SiteSpec]:
    """등록된 사이트 명세 로드. 새 사이트는 sites/ 에 추가 후 여기에 등록."""
    from tools.selector_health.sites import naver_blog, naver_smartstore

    specs = [naver_blog.SPEC, naver_smartstore.SPEC]
    return {s.key: s for s in specs}
