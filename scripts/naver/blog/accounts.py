"""네이버 블로그 다중 계정 레지스트리 (2026-08-24 도입).

이 프로젝트가 관리하는 블로그는 2개다. 서로 타깃 독자가 완전히 달라서
한 계정에 섞으면 둘 다 손해라 계정을 분리하기로 확정했다
(memory: naver-account-split-by-purpose, 2026-08-21).

  - skyjwsin  → 건축/AI 업무자동화 (제품: 적산·물량산출, 공무 플랫폼)
  - skyjwshin → 조명(반딧불 전파사) — blog.naver.com/beautiful-light

각 계정은 발행 이력 캐시를 **분리 소유**한다 — 섞이면 skyjwsin 쪽 중복
발행 방지 로직이 skyjwshin 글까지 걸러버리거나(또는 반대로 걸러야 할
중복을 놓치는) 오작동을 일으킨다.

기본 계정(`DEFAULT_ACCOUNT`)은 skyjwsin이다 — 계정 인자를 안 받는
기존 호출부의 동작을 그대로 유지하기 위함(하위호환).
"""

from __future__ import annotations

DEFAULT_ACCOUNT = "skyjwsin"

BLOG_ACCOUNTS: dict[str, dict] = {
    "skyjwsin": {
        "blog_id": "skyjwsin",
        "domain": "건설공무",
        "label": "AI 업무자동화 연구소",
        "cache_file": "data/blog_topic_cache_skyjwsin.json",
    },
    "skyjwshin": {
        "blog_id": "skyjwshin",
        "domain": "조명인테리어",
        "label": "반딧불 전파사 조명 이야기",
        "cache_file": "data/blog_topic_cache_skyjwshin.json",
        # 2026-08-22 이 계정에서 blog.naver.com/beautiful-light 로 주소를 직접
        # 바꿨다(네이버 정책상 1회성, 되돌릴 수 없음) — blog_id(로그인 계정)와
        # 공개 주소가 다르니 혼동하지 않는다.
        "public_url": "https://blog.naver.com/beautiful-light",
        # 2026-08-24 시점: 조명 주제 리서치가 아직 없다. 건설 블로그처럼
        # 카페 빈도+검색광고+지식iN 3중 검증을 거친 주제 풀이 없으므로,
        # 이 계정으로 자동 주제 생성/발행을 돌리면 안 된다 — 먼저 리서치가
        # 필요하다(naver_blog_content_standard.md 1절과 같은 과정).
        "topic_research_ready": False,
    },
}


def get_account(blog_id: str | None = None) -> dict:
    """계정 설정을 반환한다. blog_id가 None이면 기본 계정(skyjwsin)."""
    key = blog_id or DEFAULT_ACCOUNT
    if key not in BLOG_ACCOUNTS:
        raise ValueError(f"등록되지 않은 블로그 계정: {key} (등록: {list(BLOG_ACCOUNTS)})")
    return BLOG_ACCOUNTS[key]


def cache_file_for(blog_id: str | None = None) -> str:
    return get_account(blog_id)["cache_file"]
