"""콘텐츠 자동화 서브패키지.

포함:
  - seo_optimizer: SEO 최적화
(review_automation 은 스마트스토어 전용이라 scripts/naver/smartstore/automation/ 로 옮겼다)
"""
from __future__ import annotations

__all__ = [
    "SEOOptimizer",
]


def __getattr__(name):
    if name == "SEOOptimizer":
        from .seo_optimizer import SEOOptimizer
        return SEOOptimizer
    raise AttributeError(name)
