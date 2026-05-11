"""Official Alternative Route Finder — 보안프로그램 설치 전 공식 대체 경로를 찾는다."""
from __future__ import annotations

from typing import Any

# 경로 타입
ROUTE_OFFICIAL_API = "OFFICIAL_API"
ROUTE_MOBILE_APP = "MOBILE_APP"
ROUTE_NO_INSTALL_WEB = "NO_INSTALL_WEB"
ROUTE_NONE = "NONE"

# 도메인별 공식 대체 경로 매핑 (사용자 안내용 — 실제 접속은 사용자 결정)
_ALTERNATIVES: dict[str, list[dict[str, Any]]] = {
    "kbstar.com": [
        {
            "route_type": ROUTE_MOBILE_APP,
            "name": "KB스타뱅킹",
            "official_url": "https://obank.kbstar.com/quics?page=C040528",
            "description": "모바일 앱은 자체 보안만 사용 — 추가 보안프로그램 설치 불필요",
            "confidence": "HIGH",
        },
    ],
    "wooribank.com": [
        {
            "route_type": ROUTE_MOBILE_APP,
            "name": "우리WON뱅킹",
            "official_url": "https://spot.wooribank.com/pot/Dream",
            "description": "모바일 앱은 자체 보안만 사용",
            "confidence": "HIGH",
        },
    ],
    "gov.kr": [
        {
            "route_type": ROUTE_MOBILE_APP,
            "name": "정부24 모바일 앱",
            "official_url": "https://www.gov.kr/portal/main/mobileApp",
            "description": "모바일 앱 사용 시 PC 보안프로그램 설치 불필요",
            "confidence": "HIGH",
        },
        {
            "route_type": ROUTE_NO_INSTALL_WEB,
            "name": "정부24 무설치 조회",
            "official_url": "https://www.gov.kr/portal/main",
            "description": "일부 단순 조회는 무설치 가능",
            "confidence": "MEDIUM",
        },
    ],
    "hometax.go.kr": [
        {
            "route_type": ROUTE_MOBILE_APP,
            "name": "손택스 모바일 앱",
            "official_url": "https://www.hometax.go.kr",
            "description": "모바일 앱(손택스) 사용 시 PC 보안프로그램 일부 불필요",
            "confidence": "HIGH",
        },
    ],
}

# 결제/송금/투찰 페이지 키워드 — 대체 경로가 있어도 USER_DIRECT
_HIGH_RISK_KEYWORDS = ("결제", "송금", "투찰", "이체", "출금", "전자서명")


def find_alternatives(
    target_host: str,
    page_title: str = "",
    page_text: str = "",
) -> dict[str, Any]:
    """대상 사이트의 공식 대체 경로를 찾는다."""
    root = _root_domain(target_host)
    candidates = _ALTERNATIVES.get(root, [])

    # 고위험 페이지는 대체 경로 있어도 사용자 선택 필요
    is_high_risk = any(kw in (page_title + page_text) for kw in _HIGH_RISK_KEYWORDS)

    if not candidates:
        return {
            "alternative_available": False,
            "route_type": ROUTE_NONE,
            "official_url": None,
            "confidence": "LOW",
            "requires_user_choice": False,
            "candidates": [],
            "is_high_risk": is_high_risk,
            "server_browser_used": False,
        }

    # 가장 높은 confidence 우선
    best = sorted(candidates, key=lambda c: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(c["confidence"], 3))[0]

    return {
        "alternative_available": True,
        "route_type": best["route_type"],
        "official_url": best["official_url"],
        "confidence": best["confidence"],
        "requires_user_choice": True,
        "candidates": candidates,
        "is_high_risk": is_high_risk,
        "server_browser_used": False,
    }


def has_mobile_alternative(target_host: str) -> bool:
    """모바일 앱 대체 경로 존재 여부."""
    root = _root_domain(target_host)
    candidates = _ALTERNATIVES.get(root, [])
    return any(c["route_type"] == ROUTE_MOBILE_APP for c in candidates)


def _root_domain(host: str) -> str:
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "go", "or", "ne", "ac"):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host
