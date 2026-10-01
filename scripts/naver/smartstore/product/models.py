"""스마트스토어 상품 등록 표준 데이터 모델 + 검증.

dataclass 기반 ProductData / GeneralProductData.
__post_init__에서 자동 검증 (가격>0, 재고>=0, 이미지 파일 존재 등).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


class ValidationError(ValueError):
    """상품 데이터 검증 실패."""

    pass


@dataclass
class GeneralProductData:
    """일반 상품 등록용 표준 데이터 모델."""

    name: str
    price: int
    stock: int
    category: str | None = None
    main_image: str | None = None
    additional_images: list[str] = field(default_factory=list)
    brand: str | None = None
    manufacturer: str | None = None
    model_name: str | None = None
    description: str | None = None
    vat_type: str | None = None  # "과세상품" / "면세상품" / "영세상품"
    product_status: str | None = None  # "신상품" / "중고상품"
    minor_purchase: bool = True
    kc_exemption: str | None = None
    gift: str | None = None
    event_text: str | None = None

    def __post_init__(self) -> None:
        errors = []
        if not self.name or not self.name.strip():
            errors.append("name: 필수")
        if len(self.name) > 100:
            errors.append("name: 100자 초과")
        if self.price is not None and self.price <= 0:
            errors.append(f"price: 0보다 커야 함 (현재 {self.price})")
        if self.stock is not None and self.stock < 0:
            errors.append(f"stock: 음수 불가 (현재 {self.stock})")
        if self.main_image and not Path(self.main_image).exists():
            errors.append(f"main_image: 파일 없음 ({self.main_image})")
        for img in self.additional_images:
            if not Path(img).exists():
                errors.append(f"additional_images: 파일 없음 ({img})")
        errors.extend(self._choice_errors())
        if errors:
            raise ValidationError("\n  ".join(["상품 데이터 검증 실패:"] + errors))  # noqa: RUF005

    def _choice_errors(self) -> list[str]:
        errors: list[str] = []
        if self.vat_type and self.vat_type not in ("과세상품", "면세상품", "영세상품"):
            errors.append(f"vat_type: 잘못된 값 ({self.vat_type})")
        if self.product_status and self.product_status not in ("신상품", "중고상품"):
            errors.append(f"product_status: 잘못된 값 ({self.product_status})")
        if self.kc_exemption and self.kc_exemption not in ("구매대행", "안전기준 준수", "KC 안전관리대상 아님"):
            errors.append(f"kc_exemption: 잘못된 값 ({self.kc_exemption})")
        return errors

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != [] and v != ""}

    @classmethod
    def from_dict(cls, data: dict) -> GeneralProductData:
        # 알려진 필드만 추출 (extra 무시)
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class GroupProductData:
    """그룹상품 등록용 표준 데이터 모델 (가격/재고 없음)."""

    name: str
    category: str | None = None
    model_name: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    self_made: bool | None = None
    vat_type: str | None = None
    product_status: str | None = None
    minor_purchase: bool | None = None
    sale_period: bool | None = None
    kc_exemption: str | None = None
    certification: dict | None = None  # {agency, number}
    gift: str | None = None
    event_text: str | None = None
    main_image: str | None = None
    additional_images: list[str] = field(default_factory=list)
    image_mode: str = "common"  # "common" / "per_product"
    description: str | None = None

    def __post_init__(self) -> None:
        errors = []
        if not self.name or not self.name.strip():
            errors.append("name: 필수")
        if len(self.name) > 100:
            errors.append("name: 100자 초과")
        if self.main_image and not Path(self.main_image).exists():
            errors.append("main_image: 파일 없음")
        for img in self.additional_images:
            if not Path(img).exists():
                errors.append(f"additional_images: 파일 없음 ({img})")
        if errors:
            raise ValidationError("\n  ".join(["그룹상품 데이터 검증 실패:"] + errors))  # noqa: RUF005

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None and v != [] and v != ""}

    @classmethod
    def from_dict(cls, data: dict) -> GroupProductData:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class RegisterResult:
    """등록 결과 표준 모델."""

    ok: bool
    product_name: str
    type: str  # "general" / "group"
    saved: bool
    steps: list[tuple]  # [(step_name, result_dict)]
    error: str | None = None
    url: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)
