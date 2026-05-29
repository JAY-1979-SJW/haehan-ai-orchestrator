"""스마트스토어 상품 셀렉터 집중 관리.

네이버 UI 변경 시 이 파일만 수정.
각 필드는 [primary, ...fallbacks] 순서로 시도.

섹션 구성 (상품 등록 폼 #/products/create 기준):
  1. 카테고리       6. 즉시할인      11. 추가이미지    16. 상품정보제공고시
  2. 그룹상품관리   7. 부가세        12. 동영상        17. 검색설정
  3. 예약구매       8. 재고수량      13. 상세설명      18. 노출채널
  4. 상품명         9. 옵션          14. 상품주요정보
  5. 판매가         10. 대표이미지   15. 사이즈
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# 상품 목록 / 상세 조회용
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_ROW_LINK = [
    "tbody tr td a[href*='products']",
    "tbody tr td a[href*='productNo']",
    "tbody tr a",
]

DETAIL_URL_PATTERN     = "sell.smartstore.naver.com/#/products/"
DETAIL_URL_PATTERN_ALT = "sell.smartstore.naver.com/#/channel-products/"

PRODUCT_ID = [
    '[class*="productNo"] span',
    '[class*="product-no"]',
]

CHANNEL_PRODUCT_ID = [
    '[class*="channelProductNo"] span',
    '[class*="channel-product-no"]',
]

PRODUCT_STATUS = [
    '.product-status-badge',
    '.sale-status span',
    '[class*="saleStatus"]',
    '[class*="sale-status"]',
]

VIEW_COUNT   = ['[class*="viewCount"] span',  'td:contains("조회수") + td']
ORDER_COUNT  = ['[class*="orderCount"] span',  'td:contains("주문수") + td']
REVIEW_COUNT = ['[class*="reviewCount"] span', '.review-count']
REVIEW_SCORE = ['[class*="reviewScore"]',      '.review-score .score']


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 1. 카테고리
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_SEARCH_INPUT = [
    'input[placeholder*="카테고리명 입력"]',
    'input[ng-model="vm.category"]',
    'input[name="category"]',
    'input[placeholder*="카테고리명 검색"]',
]

CATEGORY_TEMPLATE_BTN = [
    'button:has-text("카테고리 템플릿")',
    '.btn-category-template',
]

# 조회 결과 목록에서 항목 클릭 (동적 li)
CATEGORY_RESULT_ITEM = [
    ".selectize-dropdown .option",          # Selectize 드롭다운 결과 (실제 확인)
    ".selectize-dropdown-content .option",  # 동일, 명시적 경로
    ".category-list li",
    "[class*='category'] li",
    "ul.autocomplete li",
]

# 선택된 카테고리 경로 표시
CATEGORY_PATH_DISPLAY = [
    '.category-path',
    '[class*="categoryPath"]',
    '[class*="selected-category"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 3. 예약구매
# ══════════════════════════════════════════════════════════════════════════════

PRE_ORDER_ON  = 'input[name="preOrder1"][ng-model="vm.isPreOrderOn"][value="true"]'
PRE_ORDER_OFF = 'input[name="preOrder1"][ng-model="vm.isPreOrderOn"][value="false"]'
PRE_ORDER_START = 'input[ng-model="vm.startDateModel"]'
PRE_ORDER_END   = 'input[ng-model="vm.endDateModel"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 4. 상품명
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_NAME = [
    'input[name="product.name"]',
    'input[ng-model="vm.product.name"]',
    'input[placeholder*="상품명"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 5. 판매가
# ══════════════════════════════════════════════════════════════════════════════

SALE_PRICE = [
    'input[name="product.salePrice"]',
    'input[ng-model="vm.product.salePrice"]',
    'input[placeholder*="판매가"]',
]

ORIGINAL_PRICE = [
    'input[name="product.retailPrice"]',
    'input[ng-model="vm.product.retailPrice"]',
    'input[placeholder*="정가"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 6. 즉시할인
# ══════════════════════════════════════════════════════════════════════════════

DISCOUNT_ON  = 'input[name="sale2"][ng-model="vm.viewData.isEnableImmediateDiscountPolicy"][value="true"]'
DISCOUNT_OFF = 'input[name="sale2"][ng-model="vm.viewData.isEnableImmediateDiscountPolicy"][value="false"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 7. 부가세
# ══════════════════════════════════════════════════════════════════════════════

TAX_TAXABLE  = 'input[name="surtax"][ng-model="vm.product.detailAttribute.taxType"][value="TAX"]'
TAX_EXEMPT   = 'input[name="surtax"][ng-model="vm.product.detailAttribute.taxType"][value="FREE"]'
TAX_ZERO     = 'input[name="surtax"][ng-model="vm.product.detailAttribute.taxType"][value="SMALL"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 8. 재고수량
# ══════════════════════════════════════════════════════════════════════════════

STOCK = [
    'input[name="product.stockQuantity"]',
    'input[ng-model="vm.product.stockQuantity"]',
    'input[placeholder*="재고"]',
]

MIN_PURCHASE = [
    'input[name="product.minPurchaseQuantity"]',
    'input[ng-model="vm.product.minPurchaseQuantity"]',
    'input[placeholder*="최소 구매"]',
]

MAX_PURCHASE = [
    'input[name="product.maxPurchaseQuantity"]',
    'input[ng-model="vm.product.maxPurchaseQuantity"]',
    'input[placeholder*="최대 구매"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 9. 옵션
# ══════════════════════════════════════════════════════════════════════════════

OPTION_USE_ON  = 'input[ng-model="vm.isChoiceType"][value="true"]'
OPTION_USE_OFF = 'input[ng-model="vm.isChoiceType"][value="false"]'

OPTION_SINGLE_TYPE = 'input[ng-model="vm.choiceType"][value="SINGLE"]'
OPTION_COMBINATION_TYPE = 'input[ng-model="vm.choiceType"][value="COMBINATION"]'

OPTION_NAME_INPUT  = 'input[ng-model="choiceOptionInput.groupName"]'
OPTION_VALUE_INPUT = 'input[ng-model="choiceOptionInput.name"]'
OPTION_COUNT_INPUT = 'input[ng-model="vm.choiceOptionNameCount"]'

OPTION_TABLE = [
    'table.option-management-table',
    'table[class*="optionTable"]',
    '[class*="option-list"] table',
]

# 직접입력 라디오
OPTION_DIRECT_INPUT = 'input[ng-model="vm.choiceInputType"][value="DIRECT"]'

# 옵션 적용 버튼
OPTION_APPLY_BTN = [
    'button:has-text("옵션 적용")',
    'button:has-text("적용")',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 10. 대표이미지 / 섹션 11. 추가이미지
# ══════════════════════════════════════════════════════════════════════════════

# 숨겨진 업로드 상태 hidden inputs
MAIN_IMAGE_UPLOAD_NAMES    = 'input[name="_hidden_uploaded_names"][ng-model="vm.uploadedNames"]'
MAIN_IMAGE_UPLOAD_ALL      = 'input[name="_hidden_uploaded_upload_all_names"]'
MAIN_IMAGE_MIN_SIZE        = 'input[name="_hidden_uploaded_upload_minSize"]'
MAIN_IMAGE_MAX_SIZE        = 'input[name="_hidden_uploaded_upload_maxSize"]'
MAIN_IMAGE_SQUARE          = 'input[name="_hidden_uploaded_upload_square"]'

# 실제 파일 업로드 input (대표이미지 섹션 내부)
MAIN_IMAGE_FILE_INPUT = [
    'input[type="file"]',
    '[class*="representative"] input[type="file"]',
    '[class*="main-image"] input[type="file"]',
]

# 대표이미지 미리보기
MAIN_IMAGE_PREVIEW = [
    '.representative-image img',
    '[class*="representativeImage"] img',
    '[class*="mainImage"] img',
]

# 추가이미지
ADDITIONAL_IMAGES_PREVIEW = [
    '.additional-images img',
    '[class*="additionalImage"] img',
    '.sub-image-list img',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 12. 동영상
# ══════════════════════════════════════════════════════════════════════════════

VIDEO_TITLE = [
    'input[name="videos0.title"]',
    'input[ng-model="vm.product.videos[0].title"]',
]

VIDEO_URL = [
    'input[name="videos0.url"]',
    'input[ng-model="vm.product.videos[0].representVideoId"]',
    'input[placeholder*="동영상 URL"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 13. 상세설명
# ══════════════════════════════════════════════════════════════════════════════

DESCRIPTION_SMART_EDITOR_BTN = [
    'button:has-text("스마트 에디터 ONE 으로 작성")',
    'button:has-text("스마트에디터")',
]

DESCRIPTION_AI_BTN = [
    'button:has-text("AI 상품설명 작성하기")',
    'button:has-text("AI AI 상품설명 작성하기")',
]

DESCRIPTION_IFRAME = [
    'iframe.se-iframe',
    'iframe[title*="에디터"]',
    'iframe[class*="editor"]',
    '.se-container iframe',
]

DESCRIPTION_TEXT = [
    '[class*="description"] textarea',
    'textarea[name*="description"]',
    'textarea[placeholder*="상세"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 14. 상품 주요정보 (원산지, 상품상태)
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_SELF_MADE = 'input[ng-model="vm.product.detailAttribute.itselfProductionProductYn"]'

PRODUCT_TYPE_NEW  = 'input[ng-model="vm.product.saleType"][value="NEW"]'
PRODUCT_TYPE_USED = 'input[ng-model="vm.product.saleType"][value="USED"]'

BRAND_INPUT = [
    'input[ng-model="vm.brand"]',
    'input[placeholder*="브랜드를 입력"]',
]

MANUFACTURER_INPUT = [
    'input[ng-model="vm.manufacturer"]',
    'input[placeholder*="제조사를 입력"]',
]

ORIGIN_INPUT = [
    'input[ng-model*="originCountry"]',
    'input[placeholder*="원산지"]',
]


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 15. 사이즈
# ══════════════════════════════════════════════════════════════════════════════

SIZE_ON  = 'input[ng-model="vm.isSizeOn"][value="true"]'
SIZE_OFF = 'input[ng-model="vm.isSizeOn"][value="false"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 17. 검색설정 (키워드 태그)
# ══════════════════════════════════════════════════════════════════════════════

SEARCH_KEYWORD_INPUT = [
    'input[ng-model="vm.searchKeyword"]',
    'input[placeholder*="키워드"]',
    'input[placeholder*="태그"]',
]

SEARCH_KEYWORD_ON  = 'input[ng-model="vm.isSearchTagOn"][value="true"]'
SEARCH_KEYWORD_OFF = 'input[ng-model="vm.isSearchTagOn"][value="false"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 18. 노출채널
# ══════════════════════════════════════════════════════════════════════════════

CHANNEL_SMARTSTORE   = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].channelServiceType"]'
CHANNEL_NAVER_SHOP   = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].epInfo.naverShoppingRegistration"]'
CHANNEL_DISPLAY_ON   = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].channelProductDisplayStatusType"][value="ON"]'
CHANNEL_DISPLAY_OFF  = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].channelProductDisplayStatusType"][value="SUSPENSION"]'
CHANNEL_EXCLUSIVE    = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].storeKeepExclusiveProduct"]'


# ══════════════════════════════════════════════════════════════════════════════
# 저장 버튼
# ══════════════════════════════════════════════════════════════════════════════

BTN_SAVE      = ['button:has-text("저장하기")']
BTN_TEMP_SAVE = ['button:has-text("임시저장")']
BTN_PREVIEW   = ['button:has-text("미리보기")']
BTN_CANCEL    = ['button:has-text("취소")']


# ══════════════════════════════════════════════════════════════════════════════
# 배송 (기존 호환)
# ══════════════════════════════════════════════════════════════════════════════

DELIVERY_FEE = [
    'input[name*="deliveryFee"]',
    'input[placeholder*="배송비"]',
]

DELIVERY_METHOD = [
    '[class*="deliveryMethod"] .selected',
    'select[name*="deliveryMethod"]',
]
