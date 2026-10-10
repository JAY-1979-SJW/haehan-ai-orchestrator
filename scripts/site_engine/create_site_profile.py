"""
신규 사이트 profile 생성 도구

코드 수정 없이 site profile을 생성하고 레지스트리에 등록한다.
password/OTP/cookie 관련 자동화는 생성하지 않는다.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.agent_runtime.runtime.site_profile.selector_pack_registry import (  # noqa: E402
    generate_skeleton_pack,
    register_selector_pack,
)
from core.agent_runtime.runtime.site_profile.site_profile_registry import (  # noqa: E402
    _COMMON_BLOCKED,
    _COMMON_DIRECT,
    CAT_FORUM,
    LOGIN_WAITING_AUTH,
    get_site_profile,
    register_site_profile,
)


def create_site_profile(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    site_id: str,
    display_name: str,
    domains: list[str],
    category: str,
    login_policy: str = LOGIN_WAITING_AUTH,
    supported_capabilities: list[str] | None = None,
    delegated_actions: list[str] | None = None,
    notes: str = "",
) -> dict:
    """
    site profile을 생성하고 레지스트리에 등록한다.

    금지:
    - 로그인 자동화 코드 생성 없음
    - password/OTP/cookie selector 생성 없음
    """
    profile = {
        "site_id": site_id,
        "display_name": display_name,
        "domains": domains,
        "category": category,
        "default_execution": "LOCAL_BROWSER_DEFAULT",
        "login_policy": login_policy,
        "supported_capabilities": supported_capabilities
        or [
            "READONLY_EXPLORE",
            "SEARCH",
            "EXTRACT_TEXT",
        ],
        "delegated_actions": delegated_actions or [],
        "direct_required_actions": list(_COMMON_DIRECT),
        "blocked_actions": list(_COMMON_BLOCKED),
        "max_default_executions": 1,
        "requires_audit_log": True,
        "notes": notes,
    }
    register_site_profile(profile)

    # selector pack skeleton 생성
    skeleton = generate_skeleton_pack(site_id)
    with contextlib.suppress(ValueError):  # 이미 등록된 경우
        register_selector_pack(site_id, skeleton["selectors"])

    created = get_site_profile(site_id)
    if created is None:  # 방금 등록한 프로필이 없다 — 이전에는 None 을 그대로 돌려줬다(반환 타입은 dict)
        raise ValueError(f"등록한 사이트 프로필을 찾을 수 없습니다: {site_id}")
    return created


if __name__ == "__main__":
    # 예시 실행
    result = create_site_profile(
        site_id="example_forum",
        display_name="예시 포럼",
        domains=["forum.example.com"],
        category=CAT_FORUM,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE",
            "SEARCH",
            "EXTRACT_TEXT",
            "PUBLISH_WITH_PERMISSION",
            "COMMENT_WITH_PERMISSION",
        ],
        delegated_actions=["forum_post_write", "forum_comment_write"],
        notes="예시 포럼 사이트.",
    )
    print(f"생성 완료: {result['site_id']}")
    print(f"  도메인: {result['domains']}")
    print(f"  위임 action: {result['delegated_actions']}")


def main():
    """CLI 진입점 — 샘플 사이트 프로파일 생성."""
    import sys

    site = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"[create-profile] 사이트 URL: {site or '(미지정)'}")
    print("  사이트 프로파일 생성은 인터랙티브 입력이 필요합니다.")
    print("  scripts/site_engine/create_site_profile.py 직접 편집 후 실행하세요.")
