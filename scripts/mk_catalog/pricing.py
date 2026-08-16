"""MK 카탈로그 제품코드 → 공급가(매입가) 파싱.

규칙(사업자 확인, 2026-07-17): 코드 `AAA-BBB-CCC-DDD`의 마지막 두 블록(CCC-DDD)을
이어붙인 숫자가 공급가. 예: 422-001-019-800 → "019"+"800" → 19800원.

⚠️ 공급가는 원가이므로 고객용 상세페이지/블로그/카페에 절대 노출 금지.
"""

from __future__ import annotations

import re

_CODE_RE = re.compile(r"^\d{3}-\d{3}-\d{3,4}-\d{3}$")


class InvalidCodeError(ValueError):
    pass


def parse_price(code: str) -> int:
    """제품코드에서 공급가(원)를 파싱. 형식이 아니면 InvalidCodeError."""
    code = (code or "").strip()
    if not _CODE_RE.match(code):
        raise InvalidCodeError(f"코드 형식이 아님: {code!r} (예상: 999-999-999-999)")
    parts = code.split("-")
    return int(parts[-2] + parts[-1])
