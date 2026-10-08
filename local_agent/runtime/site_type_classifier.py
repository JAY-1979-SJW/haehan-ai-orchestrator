"""Site Type Classifier — 처음 보는 사이트도 유형을 추정한다."""

from __future__ import annotations

from typing import Any

# 사이트 유형 상수
SITE_CONTENT_PLATFORM = "content_platform"
SITE_BLOG = "blog"
SITE_CAFE_OR_FORUM = "cafe_or_forum"
SITE_NOTICE_BOARD = "notice_board"
SITE_GOVERNMENT = "government"
SITE_FINANCIAL = "financial"
SITE_ECOMMERCE = "ecommerce"
SITE_DOCUMENT_PORTAL = "document_portal"
SITE_FORM_SITE = "form_site"
SITE_UNKNOWN = "unknown"

_ALL_SITE_TYPES = [
    SITE_CONTENT_PLATFORM,
    SITE_BLOG,
    SITE_CAFE_OR_FORUM,
    SITE_NOTICE_BOARD,
    SITE_GOVERNMENT,
    SITE_FINANCIAL,
    SITE_ECOMMERCE,
    SITE_DOCUMENT_PORTAL,
    SITE_FORM_SITE,
    SITE_UNKNOWN,
]

# domain 기반 known 분류
_KNOWN_DOMAIN_MAP: dict[str, str] = {
    "naver.com": SITE_CONTENT_PLATFORM,
    "blog.naver.com": SITE_BLOG,
    "cafe.naver.com": SITE_CAFE_OR_FORUM,
    "daum.net": SITE_CONTENT_PLATFORM,
    "tistory.com": SITE_BLOG,
    "g2b.go.kr": SITE_GOVERNMENT,
    "hometax.go.kr": SITE_GOVERNMENT,
    "gov.kr": SITE_GOVERNMENT,
    "mois.go.kr": SITE_GOVERNMENT,
    "nhis.or.kr": SITE_GOVERNMENT,
    "korea.kr": SITE_GOVERNMENT,
    "instagram.com": SITE_CONTENT_PLATFORM,
    "twitter.com": SITE_CONTENT_PLATFORM,
    "x.com": SITE_CONTENT_PLATFORM,
    "youtube.com": SITE_CONTENT_PLATFORM,
}

# 텍스트 힌트 → 사이트 유형 (우선순위 순)
_TEXT_HINTS: list[tuple[str, list[str]]] = [
    (SITE_GOVERNMENT, ["나라장터", "g2b", "정부", "gov", "행정", "민원", "공공기관", "go.kr"]),
    (SITE_FINANCIAL, ["은행", "bank", "금융", "증권", "카드", "보험", "투자", "예금", "대출"]),
    (SITE_ECOMMERCE, ["장바구니", "결제", "구매", "배송", "쇼핑", "shop", "store"]),
    (SITE_BLOG, ["블로그", "blog", "포스팅", "posting"]),
    (SITE_CAFE_OR_FORUM, ["카페", "cafe", "포럼", "forum", "커뮤니티", "community", "게시판"]),
    (SITE_NOTICE_BOARD, ["공지사항", "notice", "공고", "announcement", "알림"]),
    (SITE_DOCUMENT_PORTAL, ["자료실", "document", "첨부파일", "download", "자료 다운"]),
    (SITE_FORM_SITE, ["신청", "등록", "apply", "register", "form", "신청서"]),
    (SITE_CONTENT_PLATFORM, ["뉴스", "news", "매거진", "콘텐츠", "article", "기사"]),
]

# known profile site_id → site_type 매핑
_PROFILE_TO_SITE_TYPE: dict[str, str] = {
    "naver": SITE_CONTENT_PLATFORM,
    "naver_blog": SITE_BLOG,
    "naver_cafe": SITE_CAFE_OR_FORUM,
    "g2b_public": SITE_GOVERNMENT,
    "hometax_placeholder": SITE_GOVERNMENT,
    "bank_placeholder": SITE_FINANCIAL,
    "card_placeholder": SITE_FINANCIAL,
    "insurance_placeholder": SITE_FINANCIAL,
    "generic_content_site": SITE_CONTENT_PLATFORM,
    "generic_government_site": SITE_GOVERNMENT,
    "generic_financial_site": SITE_FINANCIAL,
    "generic_forum_site": SITE_CAFE_OR_FORUM,
    "generic_ecommerce_site": SITE_ECOMMERCE,
}


def _best_domain_match(host: str) -> str | None:
    for domain, stype in _KNOWN_DOMAIN_MAP.items():
        if host == domain or host.endswith("." + domain):
            return stype
    return None


def _classify_by_text(text: str) -> str:
    text_lower = text.lower()
    for stype, keywords in _TEXT_HINTS:
        if any(kw.lower() in text_lower for kw in keywords):
            return stype
    return SITE_UNKNOWN


def classify_site(observation: dict[str, Any]) -> dict[str, Any]:
    """
    page observation dict를 받아 사이트 유형을 추정한다.
    반환:
      site_type: str
      confidence: "high" | "medium" | "low"
      matched_profile_id: str | None
      is_known_site: bool
    """
    host = observation.get("host", "")
    title = observation.get("title", "")
    text = observation.get("text_content", "")
    page_type_candidates = observation.get("page_type_candidates", [])

    # 1. domain 기반 known 분류
    domain_match = _best_domain_match(host)
    if domain_match:
        return {
            "site_type": domain_match,
            "confidence": "high",
            "matched_profile_id": _profile_for_type(domain_match, host),
            "is_known_site": True,
        }

    # 2. .go.kr / .gov 도메인
    if host.endswith(".go.kr") or ".gov." in host or host.endswith(".gov"):
        return {
            "site_type": SITE_GOVERNMENT,
            "confidence": "high",
            "matched_profile_id": "generic_government_site",
            "is_known_site": False,
        }

    # 3. 텍스트 기반
    all_text = " ".join([title, text] + page_type_candidates)  # noqa: RUF005
    text_match = _classify_by_text(all_text)
    if text_match != SITE_UNKNOWN:
        return {
            "site_type": text_match,
            "confidence": "medium",
            "matched_profile_id": _generic_profile_for_type(text_match),
            "is_known_site": False,
        }

    # 4. page_type_candidates 활용
    if "government" in page_type_candidates:
        return {
            "site_type": SITE_GOVERNMENT,
            "confidence": "low",
            "matched_profile_id": "generic_government_site",
            "is_known_site": False,
        }
    if "financial" in page_type_candidates:
        return {
            "site_type": SITE_FINANCIAL,
            "confidence": "low",
            "matched_profile_id": "generic_financial_site",
            "is_known_site": False,
        }

    return {
        "site_type": SITE_UNKNOWN,
        "confidence": "low",
        "matched_profile_id": None,
        "is_known_site": False,
    }


def _profile_for_type(site_type: str, host: str) -> str | None:
    # host 기반 profile ID 유추
    for profile_id, ptype in _PROFILE_TO_SITE_TYPE.items():
        if ptype == site_type and not profile_id.startswith("generic"):
            if any(seg in host for seg in profile_id.split("_")):
                return profile_id
    return _generic_profile_for_type(site_type)


def _generic_profile_for_type(site_type: str) -> str | None:
    mapping = {
        SITE_GOVERNMENT: "generic_government_site",
        SITE_FINANCIAL: "generic_financial_site",
        SITE_ECOMMERCE: "generic_ecommerce_site",
        SITE_CAFE_OR_FORUM: "generic_forum_site",
        SITE_CONTENT_PLATFORM: "generic_content_site",
        SITE_BLOG: "generic_content_site",
        SITE_NOTICE_BOARD: "generic_government_site",
        SITE_DOCUMENT_PORTAL: "generic_content_site",
        SITE_FORM_SITE: "generic_content_site",
    }
    return mapping.get(site_type)


def get_site_type_for_profile(profile_id: str) -> str:
    return _PROFILE_TO_SITE_TYPE.get(profile_id, SITE_UNKNOWN)
