"""네이버 검색광고 API — 키워드도구(월간 검색량) 조회.

인증: access license/secret key(scripts.auth.credentials 암호화 저장) 기반
HMAC-SHA256 서명. 광고 집행/과금 기능은 사용하지 않는다 — 조회 전용.

사용:
    from scripts.naver.searchad import get_keyword_stats
    stats = get_keyword_stats(["실적신고", "4대보험"])
"""

from __future__ import annotations

from scripts.naver.searchad.keyword_tool import get_keyword_stats

__all__ = ["get_keyword_stats"]
