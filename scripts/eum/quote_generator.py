"""견적서 xlsx 자동 생성 (openpyxl) — A4 세로 서식.

공급자: 해한AI엔지니어링 / 372-34-00685 / 대표 신재우
유형: 이동형 임대(90,000원/월) / 벽부형 임대(70,000원/월) / 벽부형 구매(1,200,000원)

레이아웃은 scripts/eum/shared/layout_openpyxl.py 에 위임.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Literal

sys_path_inserted = False
try:
    from scripts.eum.shared.layout_openpyxl import render_to_wb
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.eum.shared.layout_openpyxl import render_to_wb

QuoteType = Literal["이동형_임대", "벽부형_임대", "벽부형_구매"]

# 품목 순서: 이동형_임대(0) / 벽부형_임대(1) / 벽부형_구매(2)
_ITEM_ORDER: list[QuoteType] = ["이동형_임대", "벽부형_임대", "벽부형_구매"]


def _items_to_kwargs(items: list[dict]) -> dict:
    """items 리스트 → render_to_wb 키워드 인자로 변환."""
    kwargs: dict = {}
    for item in items:
        qt = item.get("quote_type", "")
        qty = item.get("quantity", 1)
        mo = item.get("months")
        idx = _ITEM_ORDER.index(qt) if qt in _ITEM_ORDER else -1
        if idx == 0:
            kwargs["qty1"] = qty
            if mo:
                kwargs["mo1"] = mo
        elif idx == 1:
            kwargs["qty2"] = qty
            if mo:
                kwargs["mo2"] = mo
        elif idx == 2:
            kwargs["qty3"] = qty
    return kwargs


def generate_combined_quote_xlsx(
    *,
    recipient: str,
    items: list[dict],
    quote_date: date | None = None,
) -> bytes:
    """통합 견적서 xlsx bytes 반환 (A4 세로)."""
    kwargs = _items_to_kwargs(items)
    wb = render_to_wb(recipient=recipient, **kwargs)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_quote_xlsx(
    *,
    recipient: str,
    quote_type: QuoteType,
    quantity: int,
    months: int | None = None,
    quote_date: date | None = None,
) -> bytes:
    """단일 유형 견적서 (하위 호환)."""
    return generate_combined_quote_xlsx(
        recipient=recipient,
        items=[{"quote_type": quote_type, "quantity": quantity, "months": months}],
        quote_date=quote_date,
    )
