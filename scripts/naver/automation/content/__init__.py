"""콘텐츠 자동화 서브패키지.

포함:
  - review_automation: 리뷰 자동 답변
  - seo_optimizer: SEO 최적화
"""
from __future__ import annotations

__all__ = [
    "ReviewAutoResponder",
    "SEOOptimizer",
]


def __getattr__(name):
    if name == "ReviewAutoResponder":
        from .review_automation import ReviewAutoResponder
        return ReviewAutoResponder
    if name == "SEOOptimizer":
        from .seo_optimizer import SEOOptimizer
        return SEOOptimizer
    raise AttributeError(name)
