"""네이버 카페 기능 Mixin — 책임별 서브믹스인 aggregator.

CafeMixin 은 read/media/article/member/activity 서브믹스인을 다중상속으로 결합한다.
각 기능 구현은 cafe_mixin_<group>.py 에 있고, 메서드 간 호출은 인스턴스(self)/MRO 로
해결된다. 공개 API(CafeMixin) 와 BrowserAgent 다중상속은 무변경.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from scripts.naver.agent_mixins.cafe_mixin_read import CafeReadMixin
from scripts.naver.agent_mixins.cafe_mixin_media import CafeMediaMixin
from scripts.naver.agent_mixins.cafe_mixin_article import CafeArticleMixin
from scripts.naver.agent_mixins.cafe_mixin_member import CafeMemberMixin
from scripts.naver.agent_mixins.cafe_mixin_activity import CafeActivityMixin


class CafeMixin(
    CafeReadMixin,
    CafeMediaMixin,
    CafeArticleMixin,
    CafeMemberMixin,
    CafeActivityMixin,
):
    """네이버 카페 기능 Mixin (서브믹스인 결합)."""
