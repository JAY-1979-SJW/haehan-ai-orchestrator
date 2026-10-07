"""네이버 검색 응답 정규화 유틸 (HTML 정리 / 가격 / 날짜).

외부 의존성 없음. 표준 라이브러리만 사용.
"""

from __future__ import annotations

import html
import re

# 네이버 검색 결과의 title/description 에 들어오는 태그는
# 보통 <b>...</b> 강조 정도. 보수적으로 모든 태그를 제거한다.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_DATE8_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
# 숫자 외 문자(콤마/공백/원 등) 제거용. 부호는 별도 보존.
_DIGITS_RE = re.compile(r"\d+")
_SIGN_RE = re.compile(r"^\s*-")


def strip_html(text: str | None) -> str:
    """HTML 태그 제거 + 엔티티 디코드 + 공백 정리."""
    if not text:
        return ""
    no_tags = _TAG_RE.sub("", str(text))
    decoded = html.unescape(no_tags)
    return _WS_RE.sub(" ", decoded).strip()


def normalize_post_date(value: str | None) -> str:
    """블로그 postdate 'YYYYMMDD' → 'YYYY-MM-DD'.

    포맷이 다르면 stripped 값을 그대로 반환 (실패하지 않음).
    """
    if value is None:
        return ""
    s = str(value).strip()
    m = _DATE8_RE.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s


def to_int_price(value: str | None) -> int | None:
    """쇼핑 lprice/hprice 문자열 → int.

    - "29,800" / "10000원" / "  29800  " 모두 29800 으로 파싱.
    - 빈 문자열/숫자 없는 값은 None.
    - 선두 '-' 부호는 보존.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    sign = -1 if _SIGN_RE.match(s) else 1
    digits = "".join(_DIGITS_RE.findall(s))
    if not digits:
        return None
    try:
        return sign * int(digits)
    except ValueError:
        return None


__all__ = [
    "normalize_post_date",
    "strip_html",
    "to_int_price",
]
