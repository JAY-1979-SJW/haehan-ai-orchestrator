"""스마트스토어 상품 등록 통합 실행기 (L3 Connector).

사용:
    from scripts.naver.smartstore.product.form_runner import ProductFormRunner

    runner = ProductFormRunner(page)
    result = runner.run({
        "category":     "패션의류",
        "name":         "프리미엄 반팔 티셔츠",
        "price":        29800,
        "stock":        100,
        "main_image":   "C:/images/main.jpg",
        "description":  "고품질 코튼 소재...",
        "keywords":     ["반팔티", "여름옷"],
        "tax_type":     "과세",
        "product_type": "신상품",
        "save":         False,   # True: 실제 저장 / False: 임시저장 / None: 저장 안 함
    })
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from playwright.sync_api import Page

from scripts.common.logger import get_logger
from scripts.naver.smartstore.product.general_product import GeneralProductRegister
from scripts.naver.smartstore.product.register_form import (
    CategorySection,
    ChannelSection,
    DescriptionSection,
    DiscountSection,
    ImageSection,
    OptionSection,
    PreOrderSection,
    PriceSection,
    ProductInfoSection,
    ProductNameSection,
    SaveSection,
    SearchTagSection,
    SizeSection,
    StockSection,
    TaxSection,
    VideoSection,
)

_log = get_logger(__name__)


@dataclass
class RegisterData:
    """상품 등록 데이터 — 전체 폼 필드."""

    # ── 필수 ────────────────────────────────────────────────────────────────
    name: str = ""
    price: int = 0
    stock: int = 0

    # ── 카테고리 ─────────────────────────────────────────────────────────────
    category: str = ""
    category_result_idx: int = 0  # 검색 결과 중 몇 번째 항목

    # ── 가격 옵션 ────────────────────────────────────────────────────────────
    original_price: int | None = None
    discount_enabled: bool = False

    # ── 재고·구매 수량 ────────────────────────────────────────────────────────
    min_purchase: int = 1
    max_purchase: int | None = None

    # ── 부가세 / 상품 상태 ───────────────────────────────────────────────────
    tax_type: str = "과세"  # 과세 / 면세 / 영세
    product_type: str = "신상품"  # 신상품 / 중고상품
    self_made: bool = False

    # ── 이미지 ──────────────────────────────────────────────────────────────
    main_image: str = ""
    additional_images: list[str] = field(default_factory=list)

    # ── 동영상 ──────────────────────────────────────────────────────────────
    video_title: str = ""
    video_url: str = ""

    # ── 상세설명 ─────────────────────────────────────────────────────────────
    description: str = ""
    description_mode: str = "direct"  # direct / smart_editor / ai(네이버) / claude(AI 자동)

    # claude 모드 전용: AI 생성 파라미터
    ai_product_data: dict = field(default_factory=dict)  # {features, keywords, target, style, ...}
    ai_image_paths: list[str] = field(default_factory=list)

    # ── 옵션 ────────────────────────────────────────────────────────────────
    options: dict[str, list[str]] = field(default_factory=dict)  # {"색상": ["블랙", "화이트"]}

    # ── 주요정보 ─────────────────────────────────────────────────────────────
    brand: str = ""
    manufacturer: str = ""
    origin: str = ""

    # ── 검색 태그 ────────────────────────────────────────────────────────────
    keywords: list[str] = field(default_factory=list)

    # ── 노출채널 ─────────────────────────────────────────────────────────────
    display: bool = True
    naver_shopping: bool = True

    # ── 예약구매 ─────────────────────────────────────────────────────────────
    pre_order: bool = False
    pre_order_start: str = ""
    pre_order_end: str = ""

    # ── 저장 옵션 ────────────────────────────────────────────────────────────
    save: bool | None = None  # True=저장 / False=임시저장 / None=저장 안 함
    require_confirm: bool = True  # 저장 전 확인 여부

    @classmethod
    def from_dict(cls, data: dict) -> RegisterData:
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def validate(self) -> list[str]:
        errors = []
        if not self.name:
            errors.append("상품명 필수")
        if len(self.name) > 100:
            errors.append(f"상품명 100자 초과 ({len(self.name)}자)")
        if self.price < 10:
            errors.append(f"판매가 최소 10원 ({self.price})")
        if self.stock < 0:
            errors.append(f"재고 0 이상 ({self.stock})")
        return errors


class ProductFormRunner:
    """상품 등록 폼 통합 실행기.

    RegisterData를 받아 각 섹션 클래스를 순서대로 호출하고
    결과를 step별로 기록합니다.
    """

    SECTION_ORDER: ClassVar[list[str]] = [
        "open",  # 1. 페이지 진입
        "category",  # 2. 카테고리
        "pre_order",  # 3. 예약구매
        "name",  # 4. 상품명
        "price",  # 5. 판매가
        "discount",  # 6. 즉시할인
        "tax",  # 7. 부가세
        "stock",  # 8. 재고수량
        "option",  # 9. 옵션
        "image",  # 10~11. 이미지
        "video",  # 12. 동영상
        "description",  # 13. 상세설명
        "product_info",  # 14. 상품 주요정보
        "keywords",  # 17. 검색설정
        "channel",  # 18. 노출채널
        "save",  # 저장
    ]

    def __init__(self, page: Page):
        self.page = page
        self._reg = GeneralProductRegister(page)

        # 섹션 인스턴스
        self.category = CategorySection(page)
        self.pre_order = PreOrderSection(page)
        self.product_name = ProductNameSection(page)
        self.price = PriceSection(page)
        self.discount = DiscountSection(page)
        self.tax = TaxSection(page)
        self.stock = StockSection(page)
        self.option = OptionSection(page)
        self.image = ImageSection(page)
        self.video = VideoSection(page)
        self.description = DescriptionSection(page)
        self.product_info = ProductInfoSection(page)
        self.size = SizeSection(page)
        self.keywords = SearchTagSection(page)
        self.channel = ChannelSection(page)
        self.save_section = SaveSection(page)

    def _auto_handle_popups(self) -> None:
        """카테고리 선택/페이지 진입 후 뜨는 팝업/모달 자동 처리 (실패는 무시)."""
        try:
            from scripts.naver.smartstore.navigation.cdp_popup_manager import CdpPopupManager

            CdpPopupManager().handle_page(self.page, auto_confirm=True)
        except Exception:  # noqa: BLE001 - 예약구매/팝업 처리를 위한 CdpPopupManager 호출 실패는 무시하고 다음 폼 입력 단계로 계속 진행
            pass

    def _run_open(self, steps: dict) -> list[str] | None:
        """1. 페이지 진입. 실패 시 errors 리스트 반환."""
        ok = self._reg.open()
        steps["open"] = {"ok": ok}
        if not ok:
            return ["상품 등록 페이지 진입 실패"]
        time.sleep(1)
        return None

    def _run_category(self, data: RegisterData, steps: dict) -> None:
        """2. 카테고리."""
        if data.category:
            steps["category"] = self.category.set(data.category, result_idx=data.category_result_idx)
            time.sleep(0.8)  # 카테고리 선택 후 폼 리렌더링 대기
            # 카테고리 선택 후 뜨는 팝업/모달 자동 처리
            self._auto_handle_popups()

    def _run_basic(self, data: RegisterData, steps: dict) -> list[str] | None:
        """3~9. 예약구매/상품명/판매가/즉시할인/부가세/재고/옵션. 필수 입력 실패 시 errors 반환."""
        # 3. 예약구매
        if data.pre_order:
            steps["pre_order"] = self.pre_order.enable(data.pre_order_start, data.pre_order_end)
        else:
            steps["pre_order"] = self.pre_order.disable()

        # 4. 상품명
        steps["name"] = self.product_name.set(data.name)
        if not steps["name"]["ok"]:
            return ["상품명 입력 실패"]

        # 5. 판매가
        steps["price"] = self.price.set(data.price, data.original_price)
        if not steps["price"]["ok"]:
            return ["판매가 입력 실패"]

        # 6. 즉시할인
        if data.discount_enabled:
            steps["discount"] = self.discount.enable()
        else:
            steps["discount"] = self.discount.disable()

        # 7. 부가세
        steps["tax"] = self.tax.set(data.tax_type)

        # 8. 재고수량
        steps["stock"] = self.stock.set(data.stock, data.min_purchase, data.max_purchase)
        if not steps["stock"]["ok"]:
            return ["재고수량 입력 실패"]

        # 9. 옵션
        if data.options:
            steps["option"] = self.option.add_single(data.options)
        else:
            steps["option"] = self.option.disable()
        return None

    def _run_media(self, data: RegisterData, steps: dict) -> None:
        """10~12. 이미지/동영상."""
        # 10~11. 이미지
        img_results: dict[str, Any] = {}
        if data.main_image:
            img_results["main"] = self.image.upload_main(data.main_image)
        if data.additional_images:
            img_results["additional"] = self.image.upload_additional(data.additional_images)
        steps["image"] = {"ok": True, **img_results}

        # 12. 동영상
        if data.video_title or data.video_url:
            steps["video"] = self.video.set(data.video_title, data.video_url)

    def _run_description(self, data: RegisterData, steps: dict) -> None:
        """13. 상세설명."""
        if data.description_mode == "claude":
            # Claude AI 자동 작성 — description 텍스트 대신 ai_product_data 사용
            ai_data = {
                "name": data.name,
                "category": data.category,
                "price": data.price,
                "brand": data.brand,
                "keywords": data.keywords,
                **data.ai_product_data,  # features, target, specs, notice, style 등 오버라이드
            }
            steps["description"] = self.description.write_claude(ai_data, image_paths=data.ai_image_paths or None)
        elif data.description:
            if data.description_mode == "smart_editor":
                steps["description"] = self.description.write_via_editor(data.description)
            elif data.description_mode == "ai":
                steps["description"] = self.description.open_ai_writer()
            else:
                steps["description"] = self.description.write_direct(data.description)

    def _run_tail(self, data: RegisterData, steps: dict) -> None:
        """14~저장: 주요정보/검색태그/노출채널/저장."""
        # 14. 상품 주요정보
        if any([data.brand, data.manufacturer, data.origin]):
            steps["product_info"] = self.product_info.set(
                brand=data.brand,
                manufacturer=data.manufacturer,
                origin=data.origin,
                product_type=data.product_type,
                self_made=data.self_made,
            )

        # 17. 검색 태그
        if data.keywords:
            steps["keywords"] = self.keywords.set(data.keywords)

        # 18. 노출채널
        steps["channel"] = self.channel.set(
            display=data.display,
            naver_shopping=data.naver_shopping,
        )

        # 저장
        if data.save is True:
            steps["save"] = self.save_section.save(require_confirm=data.require_confirm)
        elif data.save is False:
            steps["save"] = self.save_section.temp_save()
        else:
            steps["save"] = {"ok": True, "skipped": True, "note": "저장 생략"}

    def run(self, data: dict | RegisterData, skip_open: bool = False) -> dict:
        """전체 폼 실행.

        Args:
            data: RegisterData 또는 dict
            skip_open: True면 페이지 진입 생략 (이미 열려 있을 때)

        Returns:
            {ok, steps: {섹션명: {ok, ...}}, errors: [...]}
        """
        if isinstance(data, dict):
            data = RegisterData.from_dict(data)

        # 유효성 검사
        errs = data.validate()
        if errs:
            return {"ok": False, "errors": errs, "steps": {}}

        steps: dict[str, Any] = {}

        # 1. 페이지 진입
        if not skip_open:
            open_errs = self._run_open(steps)
            if open_errs:
                return {"ok": False, "errors": open_errs, "steps": steps}

        self._run_category(data, steps)

        basic_errs = self._run_basic(data, steps)
        if basic_errs:
            return {"ok": False, "errors": basic_errs, "steps": steps}

        self._run_media(data, steps)
        self._run_description(data, steps)
        self._run_tail(data, steps)

        failed = [k for k, v in steps.items() if not v.get("ok", True)]
        return {
            "ok": len(failed) == 0,
            "steps": steps,
            "failed_sections": failed,
            "errors": [steps[k].get("error", "") for k in failed],
        }

    def fill_only(self, data: dict | RegisterData) -> dict:
        """페이지 진입 없이 현재 열린 폼에만 채우기."""
        return self.run(data, skip_open=True)

    def _edit_open(self, product_id: str, steps: dict) -> dict | None:
        """1. 수정 페이지 진입. 실패 시 반환할 결과 dict, 성공이면 None."""
        EDIT_URL = f"https://sell.smartstore.naver.com/#/products/{product_id}/edit"
        try:
            self.page.goto(EDIT_URL, timeout=20000, wait_until="domcontentloaded")
            time.sleep(2.5)  # 폼 Angular 렌더링 대기
            # 팝업 처리 (임시저장 불러오기 등)
            self._auto_handle_popups()
            steps["open"] = {"ok": True, "url": EDIT_URL}
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품 등록/수정 폼 자동화(필드 입력 단계) — 팝업관리자 호출 실패는 무시하고 계속, 수정페이지 진입 실패는 에러 목록에 담아 반환할 뿐 최종 저장/제출 버튼 클릭은 별도 단계로 분리되어 있음
            return {"ok": False, "product_id": product_id, "errors": [f"수정 페이지 진입 실패: {e}"], "steps": steps}
        return None

    def _edit_fields(self, fields: dict, steps: dict) -> None:
        """2. 지정된 필드만 수정 (카테고리는 수정 불가 — 등록 후 변경 금지)."""
        if fields.get("name"):
            steps["name"] = self.product_name.set(fields["name"])

        if fields.get("price") is not None:
            steps["price"] = self.price.set(
                int(fields["price"]),
                int(fields["original_price"]) if fields.get("original_price") else None,
            )

        if "discount_enabled" in fields:
            if fields["discount_enabled"]:
                steps["discount"] = self.discount.enable()
            else:
                steps["discount"] = self.discount.disable()

        if fields.get("stock") is not None:
            steps["stock"] = self.stock.set(int(fields["stock"]))

        if fields.get("description"):
            steps["description"] = self.description.write_direct(fields["description"])

        if any(fields.get(k) for k in ("brand", "manufacturer", "origin")):
            steps["product_info"] = self.product_info.set(
                brand=fields.get("brand", ""),
                manufacturer=fields.get("manufacturer", ""),
                origin=fields.get("origin", ""),
            )

        if fields.get("keywords"):
            steps["keywords"] = self.keywords.set(fields["keywords"])

    def _edit_save(self, fields: dict, steps: dict) -> None:
        """3. 저장."""
        save = fields.get("save", False)
        if save is True:
            steps["save"] = self.save_section.save(require_confirm=False)
        elif save is False:
            steps["save"] = self.save_section.temp_save()
        else:
            steps["save"] = {"ok": True, "skipped": True}

    def edit(self, product_id: str, fields: dict) -> dict:
        """기존 상품 수정.

        Args:
            product_id: 상품번호 (숫자 문자열)
            fields:     수정할 필드만 포함한 dict
                        지원: name, price, stock, description, keywords,
                              brand, manufacturer, origin, original_price,
                              discount_enabled, save (True/False/None)

        Returns:
            {ok, product_id, steps, errors}
        """
        steps: dict[str, Any] = {}

        open_fail = self._edit_open(product_id, steps)
        if open_fail is not None:
            return open_fail

        self._edit_fields(fields, steps)
        self._edit_save(fields, steps)

        failed = [k for k, v in steps.items() if not v.get("ok", True)]
        return {
            "ok": len(failed) == 0,
            "product_id": product_id,
            "steps": steps,
            "failed_sections": failed,
            "errors": [steps[k].get("error", "") for k in failed],
        }
