"""상품 등록 사전 검증 — 브라우저를 열기 **전에** 로컬에서 걸러낸다.

배경 (2026-08-15):
    상품 등록 실패의 상당수가 브라우저까지 다녀와야 드러났다. 카테고리 오타
    하나에 60초를 쓰고, 돌아온 답은 'category_mismatch' 뿐이라 무엇으로
    고쳐야 하는지도 알 수 없었다.

    그런데 카테고리 존재 여부, 이미지 파일 유무, 상품명 길이, 가격 단위는
    전부 **로컬에서 즉시 판정 가능하다**. 브라우저는 그 뒤에 열면 된다.

심각도 3단계 — 이 구분이 이 모듈의 핵심이다:
    error        : 진행 불가. 브라우저를 아예 열지 않는다.
    sale_blocker : 임시저장은 되지만 판매개시는 막는다.
                   (예: KC 인증번호 없는 전기용품 — 판매하면 제재 대상)
    warn         : 진행하되 알린다.

    사람이 "이번엔 임시저장까지만 하자" 고 판단하던 것을 코드가 강제한다.
    판단을 사람 기억에 맡기면 언젠가 빠뜨린다.

이 모듈은 DB·API·브라우저에 의존하지 않는다(순수 판정).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scripts.naver.smartstore.product.category_resolver import (
    CategoryResolver,
    get_resolver,
)

ERROR = "error"
SALE_BLOCKER = "sale_blocker"
WARN = "warn"

# 네이버 상품명 최대 길이
MAX_NAME_LEN = 100
# 판매가 단위 / 최소가
PRICE_UNIT = 10
MIN_PRICE = 10
# 대표이미지 제약
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif")
MAX_IMAGE_BYTES = 20 * 1024 * 1024

# 판매개시 전 반드시 있어야 하는 값 (없으면 임시저장까지만 허용)
_SALE_REQUIRED: tuple[tuple[str, str], ...] = (
    ("kc_cert", "KC 인증번호 없음 — 전기용품은 안전확인 대상이라 판매 불가"),
    ("origin_area", "원산지 2단(지역) 미지정"),
    ("delivery_fee_policy", "배송비 정책 미지정"),
    ("as_phone", "A/S 전화번호 없음"),
)


@dataclass
class Issue:
    """고칠 수 있는 형태의 실패. candidates 가 있으면 그대로 재시도할 수 있다."""

    field: str
    severity: str
    message: str
    candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "severity": self.severity,
            "message": self.message,
            "candidates": list(self.candidates),
        }


@dataclass
class PreflightReport:
    issues: list[Issue] = field(default_factory=list)
    resolved: dict = field(default_factory=dict)

    @property
    def can_fill(self) -> bool:
        """False 면 브라우저를 열지 않는다."""
        return not any(i.severity == ERROR for i in self.issues)

    @property
    def can_publish(self) -> bool:
        """False 면 판매개시를 거부한다(임시저장은 가능할 수 있다)."""
        return self.can_fill and not any(i.severity == SALE_BLOCKER for i in self.issues)

    def by_severity(self, severity: str) -> list[Issue]:
        return [i for i in self.issues if i.severity == severity]

    def as_dicts(self) -> list[dict]:
        return [i.to_dict() for i in self.issues]

    def summary(self) -> str:
        if not self.issues:
            return "문제 없음"
        parts = []
        for sev, label in ((ERROR, "오류"), (SALE_BLOCKER, "판매차단"), (WARN, "경고")):
            n = len(self.by_severity(sev))
            if n:
                parts.append(f"{label} {n}건")
        return " / ".join(parts)


def _check_category(data: dict, rep: PreflightReport, resolver: CategoryResolver) -> None:
    name = (data.get("category") or "").strip()
    if not name:
        rep.issues.append(Issue("category", ERROR, "카테고리 미지정"))
        return
    if not resolver.loaded:
        # 목록을 못 읽으면 판정하지 않는다. 모르면서 막으면 정상 등록까지 막힌다.
        rep.issues.append(Issue("category", WARN, "카테고리 목록을 읽지 못해 사전 검증 생략 — 브라우저 검증에 의존"))
        return
    m = resolver.resolve(name)
    if m is None:
        rep.issues.append(
            Issue(
                "category",
                ERROR,
                f"'{name}' 카테고리가 존재하지 않음",
                resolver.candidates(name),
            )
        )
        return
    rep.resolved["category_path"] = m.path
    if resolver.is_ambiguous(name):
        rep.issues.append(
            Issue(
                "category",
                WARN,
                f"'{name}' 이 여러 경로에 존재 — 의도한 곳인지 확인 필요",
                resolver.paths_for(name)[:3],
            )
        )


def _check_name(data: dict, rep: PreflightReport) -> None:
    nm = (data.get("name") or "").strip()
    if not nm:
        rep.issues.append(Issue("name", ERROR, "상품명 없음"))
    elif len(nm) > MAX_NAME_LEN:
        rep.issues.append(Issue("name", ERROR, f"상품명 {len(nm)}자 — 최대 {MAX_NAME_LEN}자 초과"))


def _check_image(data: dict, rep: PreflightReport) -> None:
    img = data.get("main_image")
    if not img:
        rep.issues.append(Issue("main_image", ERROR, "대표이미지 없음"))
        return
    p = Path(str(img))
    if not p.exists():
        rep.issues.append(Issue("main_image", ERROR, f"이미지 파일이 없음: {p.name}"))
    elif p.suffix.lower() not in IMAGE_EXTS:
        rep.issues.append(
            Issue("main_image", ERROR, f"지원하지 않는 확장자: {p.suffix} (허용 {', '.join(IMAGE_EXTS)})")
        )
    elif p.stat().st_size > MAX_IMAGE_BYTES:
        mb = p.stat().st_size / 1024 / 1024
        rep.issues.append(Issue("main_image", ERROR, f"이미지 {mb:.1f}MB — 20MB 초과"))


def _check_price_stock(data: dict, rep: PreflightReport) -> None:
    price = data.get("price")
    if price is None:
        rep.issues.append(Issue("price", SALE_BLOCKER, "판매가 미입력"))
    elif not isinstance(price, int) or isinstance(price, bool):
        rep.issues.append(Issue("price", ERROR, f"판매가는 정수여야 함: {price!r}"))
    elif price < MIN_PRICE:
        rep.issues.append(Issue("price", ERROR, f"판매가 최소 {MIN_PRICE}원: {price}"))
    elif price % PRICE_UNIT:
        rep.issues.append(Issue("price", ERROR, f"판매가는 {PRICE_UNIT}원 단위: {price}"))

    stock = data.get("stock")
    if stock is None:
        rep.issues.append(Issue("stock", ERROR, "재고 미입력"))
    elif not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
        rep.issues.append(Issue("stock", ERROR, f"재고는 0 이상 정수여야 함: {stock!r}"))


def preflight(data: dict, resolver: CategoryResolver | None = None) -> PreflightReport:
    """등록 데이터를 로컬에서 검증한다. 브라우저를 열지 않는다."""
    rep = PreflightReport()
    r = resolver or get_resolver()

    _check_category(data, rep, r)
    _check_name(data, rep)
    _check_image(data, rep)
    _check_price_stock(data, rep)

    for key, msg in _SALE_REQUIRED:
        if not data.get(key):
            rep.issues.append(Issue(key, SALE_BLOCKER, msg))
    if not data.get("tags"):
        rep.issues.append(Issue("tags", WARN, "검색태그 없음 — 검색 노출에 불리"))

    return rep
