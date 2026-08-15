"""경쟁사 상품 상세 수집 결과 스키마.

핵심 설계 — "로직이 안 맞을 때" 대응 (2026-08-15):
    오늘 실제 사고: 목록의 '정상가'를 실판매가로 오인해 시장가를 48% 과소평가했고,
    T5/T33 범용품을 라인조명으로 섞어 세 시장가를 절반으로 왜곡했다.
    공통 원인은 **틀린 값을 확신에 차서 반환**한 것이다.

    그래서 모든 값에 다음을 강제한다:
      - source     : 어느 경로로 얻었나 (json / dom / vision)
      - confidence : high / medium / low
      - 못 찾으면 None (0 이나 추정값 금지)
      - needs_review: 자기검증 실패 시 True + 스크린샷 경로 보존
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# 값 출처
SRC_JSON = "json"  # __NEXT_DATA__ 등 구조화 데이터 (가장 신뢰)
SRC_DOM = "dom"  # DOM 조작/파싱
SRC_VISION = "vision"  # 스크린샷 비전 분석 (폴백)

CONF_HIGH = "high"
CONF_MED = "medium"
CONF_LOW = "low"


@dataclass
class Field:
    """값 + 출처 + 신뢰도. 값이 없으면 value=None 을 유지한다(0/추정 금지)."""

    value: Any = None
    source: str | None = None
    confidence: str | None = None
    note: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OptionCombo:
    """옵션 조합 1건과 그때의 실제 금액."""

    labels: list[str] = field(default_factory=list)  # 예: ["1200mm 일자 40W", "주광색 5700K"]
    extra_won: int | None = None  # 옵션 추가금 합계
    total_won: int | None = None  # 화면에 표시된 총 금액
    screenshot: str | None = None
    needs_review: bool = False
    review_reason: str = ""

    def verify(self, base_price: int | None) -> None:
        """자기검증: 총금액 == 기본가 + 추가금 인지 확인.

        안 맞으면 값을 버리지 않되 needs_review 를 세워 사람이 보게 한다.
        (숨기면 오늘 같은 조용한 오류가 반복된다)
        """
        if self.total_won is None:
            self.needs_review = True
            self.review_reason = "총금액 미확인"
            return
        if base_price is None:
            return
        if self.total_won < base_price:
            # 실측 사고(2026-08-15): 폴백이 배송비 4,000원을 총액으로 오인했다.
            # 총액이 기본가보다 작을 수는 없으므로 확실한 오류다.
            self.needs_review = True
            self.review_reason = f"총액 불신: 표시 {self.total_won:,} < 기본가 {base_price:,} — 배송비 등 오인 가능"
            return
        if self.extra_won is None:
            # 추가금을 라벨에 표기하지 않는 스토어가 있다(실측: 명정라이팅의 1단 옵션).
            # 이때 총액은 네이버가 계산한 값이므로 그대로 신뢰하고 침묵한다.
            # 0 으로 단정해 '산술 불일치' 를 만들어내면 그것이 오히려 거짓 경보다.
            return
        expected = base_price + self.extra_won
        if expected != self.total_won:
            self.needs_review = True
            self.review_reason = (
                f"산술 불일치: 기본 {base_price:,} + 옵션 {self.extra_won:,} = {expected:,} ≠ 표시 {self.total_won:,}"
            )


@dataclass
class CompetitorProduct:
    """경쟁사 상품 1건."""

    url: str = ""
    store: str = ""
    product_id: str = ""

    title: Field = field(default_factory=Field)
    base_price: Field = field(default_factory=Field)  # 화면 표시 대표가
    delivery_fee: Field = field(default_factory=Field)
    review_count: Field = field(default_factory=Field)
    rating: Field = field(default_factory=Field)
    maker: Field = field(default_factory=Field)
    origin: Field = field(default_factory=Field)
    category_path: Field = field(default_factory=Field)

    options: list[OptionCombo] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    error: str | None = None

    def flag(self, reason: str) -> None:
        self.needs_review = True
        if reason not in self.review_reasons:
            self.review_reasons.append(reason)

    def finalize(self) -> None:
        """수집 종료 시 일괄 자기검증."""
        for o in self.options:
            o.verify(self.base_price.value)
            if o.needs_review:
                self.flag(f"옵션[{' / '.join(o.labels)}] {o.review_reason}")

        if not self.title.known:
            self.flag("상품명 미확인")
        if not self.base_price.known:
            self.flag("기본가 미확인")
        if not self.options:
            self.flag("옵션 미수집 — 실구매가 산정 불가")

    # 실구매가 범위 (옵션 포함). 모르면 None.
    def price_range(self) -> tuple[int | None, int | None]:
        totals = [o.total_won for o in self.options if o.total_won is not None]
        if not totals:
            return (None, None)
        return (min(totals), max(totals))

    def to_dict(self) -> dict:
        d = asdict(self)
        lo, hi = self.price_range()
        d["price_min"] = lo
        d["price_max"] = hi
        return d
