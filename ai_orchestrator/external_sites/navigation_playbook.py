"""External Site Navigation Playbook.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

각 사이트의 진입 동선, 허용 탐색 방법, 성공/실패 마커,
URL 추측 금지 정책을 machine-readable하게 정의한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NavigationPlaybook:
    provider_id: str
    start_url: str
    allowed_navigation_methods: tuple[str, ...]
    official_menu_labels: tuple[str, ...]
    forbidden_url_guessing: bool
    known_management_urls: tuple[str, ...]
    dom_link_discovery_required: bool
    success_markers: tuple[str, ...]
    failure_markers: tuple[str, ...]
    recovery_policy: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "start_url": self.start_url,
            "allowed_navigation_methods": list(self.allowed_navigation_methods),
            "official_menu_labels": list(self.official_menu_labels),
            "forbidden_url_guessing": self.forbidden_url_guessing,
            "known_management_urls": list(self.known_management_urls),
            "dom_link_discovery_required": self.dom_link_discovery_required,
            "success_markers": list(self.success_markers),
            "failure_markers": list(self.failure_markers),
            "recovery_policy": list(self.recovery_policy),
        }


PLAYBOOKS: tuple[NavigationPlaybook, ...] = (

    NavigationPlaybook(
        provider_id="GABIA",
        start_url="https://www.gabia.com/",
        allowed_navigation_methods=(
            "navigate to start_url",
            "click official menu by label",
            "follow actual DOM href only",
            "use known_management_urls as shortcut if already confirmed",
        ),
        official_menu_labels=(
            "My가비아", "서비스 관리", "DNS 관리툴", "DNS 설정", "설정",
        ),
        forbidden_url_guessing=True,
        known_management_urls=("https://dns.gabia.com/",),
        dom_link_discovery_required=True,
        success_markers=(
            "Gabia DNS 관리",
            "haehan-ai.kr",
            "설정 버튼",
            "DNS 설정",
        ),
        failure_markers=(
            "404",
            "오류가 발생했습니다",
            "로그인 페이지 반복",
            "chromewebdata",
            "error_page",
        ),
        recovery_policy=(
            "stop immediately",
            "capture current url and title",
            "do not guess new URL",
            "request user-present login if needed",
            "report failure markers found",
        ),
    ),

    NavigationPlaybook(
        provider_id="NAVER",
        start_url="https://www.naver.com/",
        allowed_navigation_methods=(
            "navigate to start_url",
            "click official menu by label",
            "follow actual DOM href only",
        ),
        official_menu_labels=(
            "블로그", "스마트스토어", "메일", "카페", "로그인",
        ),
        forbidden_url_guessing=True,
        known_management_urls=("https://blog.naver.com/", "https://sell.smartstore.naver.com/"),
        dom_link_discovery_required=True,
        success_markers=("로그인 완료", "내 블로그", "글쓰기"),
        failure_markers=("로그인 필요", "보안 인증", "비정상 접근"),
        recovery_policy=(
            "stop",
            "request user-present login",
            "do not retry without user",
        ),
    ),

    NavigationPlaybook(
        provider_id="GOOGLE",
        start_url="https://www.google.com/",
        allowed_navigation_methods=(
            "official OAuth only",
            "Gmail API",
            "Drive API",
            "Calendar API",
        ),
        official_menu_labels=("Gmail", "Drive", "Calendar"),
        forbidden_url_guessing=True,
        known_management_urls=("https://myaccount.google.com/",),
        dom_link_discovery_required=False,
        success_markers=("OAuth 완료", "API 응답 200"),
        failure_markers=("401", "403", "invalid_grant"),
        recovery_policy=(
            "stop",
            "re-authorize via official OAuth",
            "do not store raw token",
        ),
    ),

    NavigationPlaybook(
        provider_id="HIWORKS",
        start_url="https://office.hiworks.com/",
        allowed_navigation_methods=(
            "navigate to start_url",
            "follow official menu",
            "follow DOM link",
        ),
        official_menu_labels=("메일", "메일쓰기", "받은메일함", "로그인"),
        forbidden_url_guessing=True,
        known_management_urls=("https://office.hiworks.com/",),
        dom_link_discovery_required=True,
        success_markers=("받은메일함", "메일쓰기"),
        failure_markers=("로그인 필요", "세션 만료", "404"),
        recovery_policy=(
            "stop",
            "request user-present login",
            "do not send email without approval",
        ),
    ),

    NavigationPlaybook(
        provider_id="G2B_NARA",
        start_url="https://www.g2b.go.kr/",
        allowed_navigation_methods=(
            "navigate to start_url",
            "follow official menu",
            "follow DOM link",
        ),
        official_menu_labels=("입찰", "공고", "로그인", "인증서 로그인"),
        forbidden_url_guessing=True,
        known_management_urls=("https://www.g2b.go.kr/",),
        dom_link_discovery_required=True,
        success_markers=("공고 목록", "입찰 공고"),
        failure_markers=("인증 필요", "공인인증서", "404", "접근 불가"),
        recovery_policy=(
            "stop before any submit",
            "request user-present certificate login",
            "do not store certificate password",
        ),
    ),
)

_PLAYBOOK_INDEX: dict[str, NavigationPlaybook] = {p.provider_id: p for p in PLAYBOOKS}


def get_playbook(provider_id: str) -> NavigationPlaybook | None:
    return _PLAYBOOK_INDEX.get(provider_id)


__all__ = ["NavigationPlaybook", "PLAYBOOKS", "get_playbook"]
