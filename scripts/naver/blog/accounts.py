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

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.app_paths import onedrive_root, resolve_external

DEFAULT_ACCOUNT = "skyjwsin"

BLOG_ACCOUNTS: dict[str, dict] = {
    "skyjwsin": {
        "blog_id": "skyjwsin",
        "domain": "건설공무",
        "label": "AI 업무자동화 연구소",
        "cache_file": str(data_dir() / "blog_topic_cache_skyjwsin.json"),
        # 커스텀 공개 주소 없음 — admin.blog.naver.com 링크에도 로그인 ID
        # 그대로 나온다. skyjwshin과 대비해 명시적으로 채워둔다.
        "public_alias": "skyjwsin",
    },
    "skyjwshin": {
        "blog_id": "skyjwshin",
        "domain": "조명인테리어",
        "label": "반딧불 전파사 조명 이야기",
        "cache_file": str(data_dir() / "blog_topic_cache_skyjwshin.json"),
        # 2026-08-22 이 계정에서 blog.naver.com/beautiful-light 로 주소를 직접
        # 바꿨다(네이버 정책상 1회성, 되돌릴 수 없음) — blog_id(로그인 계정)와
        # 공개 주소가 다르니 혼동하지 않는다.
        #
        # 2026-08-24 사고: admin.blog.naver.com/{alias}/... 링크의 {alias}가
        # 로그인 ID가 아니라 이 공개 주소(하이픈 포함 "beautiful-light")로
        # 나온다는 걸 모르고 verify_login()이 "skyjwshin"과 비교하다가
        # 실제로는 정상 로그인 상태인데 "로그아웃"으로 오판했다. 이 필드로
        # 어느 쪽이 admin 링크에 나오는지 명시한다.
        "public_url": "https://blog.naver.com/beautiful-light",
        "public_alias": "beautiful-light",
        # 2026-08-24: 오늘의집 커뮤니티 기반 3중 검증(오늘의집 빈도+검색광고+
        # 지식iN) 1차 리서치 완료 — research_blog_topics_lighting.py 참조.
        # data/blog_topic_research_lighting_latest.json 에 주제 68개 확보.
        # 다만 아직 사람이 직접 골라 쓴 적은 없다 — 자동 발행 파이프라인
        # (blog_publish_manual.py --account skyjwshin)에 그대로 물리기 전에
        # 주제 품질을 한 번 검수할 것.
        "topic_research_ready": True,
        "topic_research_file": str(data_dir() / "blog_topic_research_lighting_latest.json"),
        # 2026-08-24 사용자 요청: 작성자 정보를 모든 글 하단에 상시 노출.
        # 실제 자격증·경력(회사소개서.pdf, 승민전력 신재우 대표 이력서)에서
        # 가져온 것 — 지어낸 스펙 아님. CTA(제품/서비스 안내, 주제마다
        # Claude가 직접 작성)와는 별개로, 이건 글 내용과 무관하게 항상
        # 똑같이 붙는 "글쓴이 소개"라서 CTA 정직성 원칙(주제마다 재작성)
        # 대상이 아니다 — 고정 서명이 맞다.
        "author_signature": (
            "\n\n[글쓴이]\n"
            "신재우 (반딧불 조명 스튜디오 대표)\n"
            "전기공사산업기사 · 소방전기기사 보유\n"
            "판교 R&D센터, 위례 오벨리스크, 동탄 골든아이타워 등 대형현장 전기·소방 시공 20년 이상"
        ),
        "author_photo": str(
            resolve_external("HAEHAN_AUTHOR_PHOTO", "전등 이미지", "images", "blog_ai_batch", "author_shinjaewoo.jpg", base=onedrive_root())
        ),
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
