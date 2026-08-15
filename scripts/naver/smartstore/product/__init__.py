"""product/ 서브모듈 — 모델, 상품 등록, 고급 기능, 일괄 등록."""

from scripts.naver.smartstore.product.models import (  # noqa
    ValidationError,
    GeneralProductData,
    GroupProductData,
    RegisterResult,
)
from scripts.naver.smartstore.product.product import ProductRegister
from scripts.naver.smartstore.product.category_resolver import (
    CategoryMatch,
    CategoryResolver,
    get_resolver,
)
from scripts.naver.smartstore.product.general_product import GeneralProductRegister
from scripts.naver.smartstore.product.modal_guard import (
    assert_no_modal,
    dismiss_blocking_modals,
    peek_modal,
)
from scripts.naver.smartstore.product.option_grid import OptionGrid
from scripts.naver.smartstore.product.tag_section import (
    MAX_TAG_BYTES,
    MAX_TAGS,
    TagSection,
    tag_byte_len,
    validate_tags,
)
from scripts.naver.smartstore.product.preflight import (
    ERROR,
    SALE_BLOCKER,
    WARN,
    Issue,
    PreflightReport,
    preflight,
)
from scripts.naver.smartstore.product.advanced import SmartEditorONE, PriceStockEditor, ProductOptionEditor
from scripts.naver.smartstore.product.bulk import BulkRegister, get_register_history
from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder  # noqa
from scripts.naver.smartstore.product.order_shipping import OrderShippingProcessor, CARRIERS  # noqa
from scripts.naver.smartstore.product.product_delete import ProductDeleter  # noqa
from scripts.naver.smartstore.product.register_form import (
    CategorySection,
    PreOrderSection,
    ProductNameSection,
    PriceSection,
    DiscountSection,
    TaxSection,
    StockSection,
    OptionSection,
    ImageSection,
    VideoSection,
    DescriptionSection,
    ProductInfoSection,
    SizeSection,
    SearchTagSection,
    ChannelSection,
    SaveSection,
)
from scripts.naver.smartstore.product.form_runner import ProductFormRunner, RegisterData
from scripts.naver.smartstore.product.description_editor import (
    SmartEditorSession,
    TextToolbar,
    BlockToolbar,
    ToolToolbar,
    AIWriter,
)
from scripts.naver.smartstore.product.ai_description_writer import (
    AIDescriptionWriter,
    generate_description,
    write_description,
    preview_description,
    validate_product_data,
    REQUIRED_FIELDS,
    RECOMMENDED_FIELDS,
    TRUST_FIELDS,
)

__all__ = [  # noqa: RUF022
    # 모델
    "ValidationError",
    "GeneralProductData",
    "GroupProductData",
    "RegisterResult",
    # 등록 클래스 (기존)
    "ProductRegister",
    "GeneralProductRegister",
    # 사전 검증 (브라우저 없이 로컬 판정)
    "CategoryMatch",
    "CategoryResolver",
    "get_resolver",
    "Issue",
    "PreflightReport",
    "preflight",
    "ERROR",
    "SALE_BLOCKER",
    "WARN",
    # 검색태그 / 옵션 그리드 / 모달 가드
    "TagSection",
    "validate_tags",
    "tag_byte_len",
    "MAX_TAG_BYTES",
    "MAX_TAGS",
    "OptionGrid",
    "dismiss_blocking_modals",
    "peek_modal",
    "assert_no_modal",
    "SmartEditorONE",
    "PriceStockEditor",
    "ProductOptionEditor",
    "BulkRegister",
    "get_register_history",
    # 폼 섹션 (신규)
    "CategorySection",
    "PreOrderSection",
    "ProductNameSection",
    "PriceSection",
    "DiscountSection",
    "TaxSection",
    "StockSection",
    "OptionSection",
    "ImageSection",
    "VideoSection",
    "DescriptionSection",
    "ProductInfoSection",
    "SizeSection",
    "SearchTagSection",
    "ChannelSection",
    "SaveSection",
    # 통합 실행기 (신규)
    "ProductFormRunner",
    "RegisterData",
    # 상세설명 에디터
    "SmartEditorSession",
    "TextToolbar",
    "BlockToolbar",
    "ToolToolbar",
    "AIWriter",
    # AI 상세설명 자동 작성 (표준 구현방식)
    "AIDescriptionWriter",
    "generate_description",
    "write_description",
    "preview_description",
    "validate_product_data",
    "REQUIRED_FIELDS",
    "RECOMMENDED_FIELDS",
    "TRUST_FIELDS",
]
