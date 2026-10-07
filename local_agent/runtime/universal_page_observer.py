"""Universal Page Observer — 현재 페이지를 안전하게 관찰한다."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# 관찰 금지 필드 (절대 읽지 않음)
_FORBIDDEN_READ_TARGETS = frozenset([
    "password", "passwd", "pwd", "otp", "pin", "secret",
    "cert_password", "certificate_password", "npki",
    "cookie", "session", "localStorage", "sessionStorage",
    "storage_state", "token", "auth_header",
])

# page type 후보 분류 힌트
_PAGE_TYPE_HINTS: dict[str, list[str]] = {
    "notice_board":     ["공지", "notice", "announcement", "알림"],
    "article_list":     ["목록", "list", "게시판", "board", "posts"],
    "blog":             ["blog", "블로그", "포스팅", "posting"],
    "cafe_or_forum":    ["cafe", "카페", "forum", "포럼", "community"],
    "document_portal":  ["자료실", "download", "첨부", "attachment", "문서"],
    "government":       ["정부", "gov", "나라장터", "g2b", "행정", "민원"],
    "financial":        ["은행", "bank", "금융", "증권", "카드", "보험"],
    "ecommerce":        ["shop", "쇼핑", "구매", "결제", "장바구니", "order"],
    "form_site":        ["신청", "등록", "apply", "register", "form", "입력"],
    "content_platform": ["뉴스", "news", "매거진", "magazine", "콘텐츠"],
}

# action signal 키워드
_ACTION_SIGNALS: dict[str, list[str]] = {
    "search":   ["검색", "search", "찾기", "query"],
    "download": ["다운로드", "download", "첨부파일", "attachment", "파일받기"],
    "write":    ["작성", "쓰기", "글쓰기", "write", "post", "새글"],
    "edit":     ["수정", "edit", "편집"],
    "delete":   ["삭제", "delete", "지우기"],
    "publish":  ["발행", "publish", "게시", "올리기"],
    "comment":  ["댓글", "comment", "답글", "reply"],
    "submit":   ["제출", "submit", "신청", "apply", "등록"],
    "send":     ["전송", "send", "보내기", "메시지"],
    "login":    ["로그인", "login", "sign in", "signin"],
}

# risk signal 키워드
_RISK_SIGNALS: dict[str, list[str]] = {
    "payment":   ["결제", "pay", "payment", "카드", "계좌이체"],
    "sign":      ["전자서명", "e-sign", "서명", "공동인증서", "인증서"],
    "bid":       ["입찰", "bid", "낙찰", "투찰"],
    "transfer":  ["송금", "transfer", "이체", "계좌"],
    "legal":     ["계약", "contract", "법적", "agreement"],
    "auth":      ["인증", "authentication", "본인확인", "공인인증"],
}

# 인증 필요 신호
_AUTH_MARKERS: list[str] = [
    "로그인", "login", "sign in", "로그인이 필요", "로그인 후", "회원가입",
    "아이디", "비밀번호 입력", "로그아웃", "마이페이지", "내 정보",
]


def _detect_hints(text: str, hint_map: dict[str, list[str]]) -> list[str]:
    text_lower = text.lower()
    matched = []
    for key, keywords in hint_map.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(key)
    return matched


def observe_page_from_dict(page_data: dict[str, Any]) -> dict[str, Any]:
    """
    page_data: Playwright page에서 수집한 안전한 정보 dict
    {
      "url": str,
      "title": str,
      "text_content": str,   # visible text (민감 필드 제외)
      "buttons": list[str],  # visible button labels
      "links": list[str],    # anchor text
      "form_labels": list[str],
      "has_file_inputs": bool,
      "heading_texts": list[str],
    }
    반환: observation dict
    """
    url = page_data.get("url", "")
    title = page_data.get("title", "")
    text = page_data.get("text_content", "")
    buttons = page_data.get("buttons", [])
    links = page_data.get("links", [])
    form_labels = page_data.get("form_labels", [])
    headings = page_data.get("heading_texts", [])

    host = urlparse(url).hostname or ""

    # 전체 visible text (합산)
    all_text = " ".join([title, text, " ".join(buttons), " ".join(links),
                         " ".join(form_labels), " ".join(headings)])

    # 민감 필드 포함 여부 검사 (읽은 척 하면 안 됨 — 관찰만)
    forbidden_detected = [f for f in _FORBIDDEN_READ_TARGETS
                          if f in text.lower() or f in " ".join(form_labels).lower()]

    page_type_candidates = _detect_hints(all_text, _PAGE_TYPE_HINTS)
    visible_actions = _detect_hints(all_text, _ACTION_SIGNALS)
    risk_signals = _detect_hints(all_text, _RISK_SIGNALS)
    auth_signals = [m for m in _AUTH_MARKERS if m.lower() in all_text.lower()]

    # 다운로드 후보 (링크에서 파일 확장자 포함)
    _file_exts = (".pdf", ".xlsx", ".xls", ".docx", ".doc", ".hwp", ".hwpx",
                  ".zip", ".csv", ".pptx", ".txt")
    download_candidates = [lnk for lnk in links
                           if any(lnk.lower().endswith(ext) for ext in _file_exts)
                           or "download" in lnk.lower() or "첨부" in lnk]

    forms_detected = bool(form_labels) or page_data.get("has_file_inputs", False)

    return {
        "host": host,
        "url": url,
        "title": title,
        "page_type_candidates": page_type_candidates or ["unknown"],
        "visible_actions": visible_actions,
        "auth_signals": list(set(auth_signals))[:5],
        "risk_signals": risk_signals,
        "forms_detected": forms_detected,
        "download_candidates": download_candidates[:10],
        "heading_texts": headings[:10],
        "buttons_observed": buttons[:20],
        # 안전 경계 필드
        "password_value_read": False,
        "otp_value_read": False,
        "cookie_read": False,
        "session_read": False,
        "storage_state_read": False,
        "forbidden_fields_detected_in_labels": forbidden_detected,
        "server_browser_used": False,
    }


def observe_page_mock(url: str = "", title: str = "",  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
                      text: str = "", buttons: list[str] | None = None,
                      links: list[str] | None = None,
                      form_labels: list[str] | None = None,
                      headings: list[str] | None = None) -> dict[str, Any]:
    """테스트/mock용 간편 interface."""
    return observe_page_from_dict({
        "url": url,
        "title": title,
        "text_content": text,
        "buttons": buttons or [],
        "links": links or [],
        "form_labels": form_labels or [],
        "has_file_inputs": False,
        "heading_texts": headings or [],
    })
