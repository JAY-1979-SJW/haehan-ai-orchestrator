"""네이버 블로그 다중 계정 레지스트리 — 배포용 템플릿.

원본: scripts/naver/blog/accounts.py. 원본에는 이 회사의 실제 계정
(skyjwsin/skyjwshin)과 실제 작성자 이력이 들어있다. 배포용 앱에 우리
계정을 하드코딩하면 안 되므로, 구조만 가져오고 값은 전부 예시로 비웠다.

설치 시 고객이 자기 계정 정보로 이 딕셔너리를 채우거나, 별도 설정 파일
(예: config/accounts.json)에서 로드하도록 바꿔야 한다 — 이 파일은 스키마
예시다.
"""

from __future__ import annotations

DEFAULT_ACCOUNT = "example"

BLOG_ACCOUNTS: dict[str, dict] = {
    "example": {
        "blog_id": "example",  # 네이버 로그인 ID
        "domain": "업종 카테고리 (예: 건설공무, 조명인테리어)",
        "label": "블로그 표시 이름",
        "cache_file": "data/blog_topic_cache_example.json",
        # admin.blog.naver.com/{alias}/ 에서 실제로 노출되는 값.
        # 공개 주소를 커스텀 설정한 계정이면 blog_id와 다를 수 있다
        # (원본 코드 주석 참조 — 이 불일치를 놓치면 로그인 상태를 오판한다).
        "public_alias": "example",
    },
}


def get_account(blog_id: str | None = None) -> dict:
    return BLOG_ACCOUNTS.get(blog_id or DEFAULT_ACCOUNT, BLOG_ACCOUNTS[DEFAULT_ACCOUNT])
