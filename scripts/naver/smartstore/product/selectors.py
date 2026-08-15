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

DETAIL_URL_PATTERN = "sell.smartstore.naver.com/#/products/"
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
    ".product-status-badge",
    ".sale-status span",
    '[class*="saleStatus"]',
    '[class*="sale-status"]',
]

VIEW_COUNT = ['[class*="viewCount"] span', 'td:contains("조회수") + td']
ORDER_COUNT = ['[class*="orderCount"] span', 'td:contains("주문수") + td']
REVIEW_COUNT = ['[class*="reviewCount"] span', ".review-count"]
REVIEW_SCORE = ['[class*="reviewScore"]', ".review-score .score"]


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
    ".btn-category-template",
]

# 조회 결과 목록에서 항목 클릭 (동적 li)
CATEGORY_RESULT_ITEM = [
    ".selectize-dropdown .option",  # Selectize 드롭다운 결과 (실제 확인)
    ".selectize-dropdown-content .option",  # 동일, 명시적 경로
    ".category-list li",
    "[class*='category'] li",
    "ul.autocomplete li",
]

# 선택된 카테고리 경로 표시
# ⚠ 2026-08-15 실측: .category-path / categoryPath / selected-category 는 모두 없음(구버전).
#   실제로는 Selectize 위젯의 선택 아이템과, 하단 안내문(info-result)에 경로가 표시된다.
#   .selectize-input .item 은 페이지 전체 검색위젯까지 15개 잡히고 첫 항목이 '수취인명'
#   이라 쓰면 안 된다(오탐 실측 확인). info-result 만 정확히 경로를 준다.
CATEGORY_PATH_DISPLAY = [
    ".info-result.text-info strong",  # 실측: '가구/인테리어>인테리어소품>조명>인테리어조명'
    ".category-path",  # deprecated
    '[class*="categoryPath"]',  # deprecated
]

# ⚠ 자동완성 첫 항목을 무조건 고르면 안 된다.
#   "인테리어조명" 검색 시 1순위가 'LED모듈' 로 나오는 것을 실측 확인(2026-08-15).
#   반드시 원하는 경로 텍스트를 포함하는 항목을 지정해 클릭하고, 선택 결과를 검증할 것.
CATEGORY_RESULT_ITEM_EXACT_HINT = "원하는 카테고리 경로 문자열로 has_text 필터 후 클릭"


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 3. 예약구매
# ══════════════════════════════════════════════════════════════════════════════

PRE_ORDER_ON = 'input[name="preOrder1"][ng-model="vm.isPreOrderOn"][value="true"]'
PRE_ORDER_OFF = 'input[name="preOrder1"][ng-model="vm.isPreOrderOn"][value="false"]'
PRE_ORDER_START = 'input[ng-model="vm.startDateModel"]'
PRE_ORDER_END = 'input[ng-model="vm.endDateModel"]'


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

DISCOUNT_ON = 'input[name="sale2"][ng-model="vm.viewData.isEnableImmediateDiscountPolicy"][value="true"]'
DISCOUNT_OFF = 'input[name="sale2"][ng-model="vm.viewData.isEnableImmediateDiscountPolicy"][value="false"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 7. 부가세
# ══════════════════════════════════════════════════════════════════════════════

TAX_TAXABLE = 'input[name="surtax"][ng-model="vm.product.detailAttribute.taxType"][value="TAX"]'
TAX_EXEMPT = 'input[name="surtax"][ng-model="vm.product.detailAttribute.taxType"][value="FREE"]'
TAX_ZERO = 'input[name="surtax"][ng-model="vm.product.detailAttribute.taxType"][value="SMALL"]'


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

OPTION_USE_ON = 'input[ng-model="vm.isChoiceType"][value="true"]'
OPTION_USE_OFF = 'input[ng-model="vm.isChoiceType"][value="false"]'

OPTION_SINGLE_TYPE = 'input[ng-model="vm.choiceType"][value="SINGLE"]'
OPTION_COMBINATION_TYPE = 'input[ng-model="vm.choiceType"][value="COMBINATION"]'

OPTION_NAME_INPUT = 'input[ng-model="choiceOptionInput.groupName"]'
OPTION_VALUE_INPUT = 'input[ng-model="choiceOptionInput.name"]'
OPTION_COUNT_INPUT = 'input[ng-model="vm.choiceOptionNameCount"]'

OPTION_TABLE = [
    "table.option-management-table",
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


# 실측 확인된 옵션 필드 (2026-08-15)
# 기존 OPTION_TABLE / OPTION_SINGLE_TYPE / OPTION_DIRECT_INPUT / OPTION_APPLY_BTN 은
# 전부 매칭되지 않는 구버전 셀렉터다.
OPTION_NAME_COUNT = 'input[ng-model="vm.choiceOptionNameCount"]'  # 옵션명 개수
OPTION_SORT_TYPE = 'input[ng-model="vm.choiceOptionSortType"]'  # 정렬 방식
OPTION_GROUP_NAME = 'input[ng-model="choiceOptionInput.groupName"]'  # 옵션명 (예: 길이)
OPTION_VALUE_NAME = 'input[ng-model="choiceOptionInput.name"]'  # 옵션값 (예: 1200mm)


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 10. 대표이미지 / 섹션 11. 추가이미지
# ══════════════════════════════════════════════════════════════════════════════

# 숨겨진 업로드 상태 hidden inputs
MAIN_IMAGE_UPLOAD_NAMES = 'input[name="_hidden_uploaded_names"][ng-model="vm.uploadedNames"]'
MAIN_IMAGE_UPLOAD_ALL = 'input[name="_hidden_uploaded_upload_all_names"]'
MAIN_IMAGE_MIN_SIZE = 'input[name="_hidden_uploaded_upload_minSize"]'
MAIN_IMAGE_MAX_SIZE = 'input[name="_hidden_uploaded_upload_maxSize"]'
MAIN_IMAGE_SQUARE = 'input[name="_hidden_uploaded_upload_square"]'

# 실제 파일 업로드 input (대표이미지 섹션 내부)
MAIN_IMAGE_FILE_INPUT = [
    'input[type="file"]',
    '[class*="representative"] input[type="file"]',
    '[class*="main-image"] input[type="file"]',
]

# 대표이미지 미리보기
MAIN_IMAGE_PREVIEW = [
    ".representative-image img",
    '[class*="representativeImage"] img',
    '[class*="mainImage"] img',
]

# 추가이미지
ADDITIONAL_IMAGES_PREVIEW = [
    ".additional-images img",
    '[class*="additionalImage"] img',
    ".sub-image-list img",
]


# ⚠ 2026-08-15 실측: 상품등록 폼에 input[type=file] 이 **없다**.
#   a.btn-add-img 를 눌러 '내 사진 불러오기' 모달을 띄워야 file input 이 생성된다.
#   또한 이미 이미지가 채워진 슬롯은 눌러도 모달이 안 열리므로 빈 슬롯을 순회해야 한다.
IMAGE_ADD_BTN = "a.btn-add-img"
IMAGE_MODAL_FILE_INPUT = "input[type=file]"  # 모달이 열린 뒤에만 존재 (multiple 지원)
IMAGE_UPLOADED_PREVIEW = 'img[src*="phinf"], img[src*="pstatic"]'


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

# ⚠ 2026-08-15 실측: 상품등록 페이지에 iframe 이 **0개**다. 스마트에디터는
#   iframe 이 아니라 **별도 탭(#/editor)** 으로 열린다. 아래는 더 이상 매칭되지 않는다.
#   (호환을 위해 상수는 남기되, 신규 코드에서 쓰지 말 것)
DESCRIPTION_IFRAME = [
    "iframe.se-iframe",
    'iframe[title*="에디터"]',
    'iframe[class*="editor"]',
    ".se-container iframe",
]

# 상세설명 작성 모드 전환 (A 태그)
DESCRIPTION_MODE_DIRECT = ['a:has-text("직접 작성")']
DESCRIPTION_MODE_HTML = ['a:has-text("HTML 작성")']

# 상세설명 본문 입력창.
# 'HTML 작성' 모드를 켜야 나타나며(1850x240), HTML 을 그대로 넣을 수 있다.
# 이미지 속 글자는 검색에 안 잡히므로 SEO 텍스트는 여기에 넣어야 한다(2026-08-15 실측).
DESCRIPTION_TEXT = [
    'textarea[ng-model="vm.editorContent"]',
]

# 스마트에디터가 열리는 별도 탭 URL 조각 (get_page_by_url 로 잡는다)
DESCRIPTION_EDITOR_TAB_URL = "#/editor"


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 14. 상품 주요정보 (원산지, 상품상태)
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_SELF_MADE = 'input[ng-model="vm.product.detailAttribute.itselfProductionProductYn"]'

PRODUCT_TYPE_NEW = 'input[ng-model="vm.product.saleType"][value="NEW"]'
PRODUCT_TYPE_USED = 'input[ng-model="vm.product.saleType"][value="USED"]'

BRAND_INPUT = [
    'input[ng-model="vm.brand"]',
    'input[placeholder*="브랜드를 입력"]',
]

MANUFACTURER_INPUT = [
    'input[ng-model="vm.manufacturer"]',
    'input[placeholder*="제조사를 입력"]',
]

# ⚠ 2026-08-15 실측: 원산지는 input 이 아니라 **3단 SELECT** 구조다.
#   originCountry 라는 ng-model 은 존재하지 않는다(구버전 잔재).
ORIGIN_INPUT = [
    'input[ng-model*="originCountry"]',  # deprecated
    'input[placeholder*="원산지"]',  # deprecated
]

# 실측 확인된 원산지 필드 (2026-08-15) — 대분류 → 중분류 → 소분류 순 선택
ORIGIN_AREA_TYPE = 'select[ng-model="vm.viewData.originAreaInfo.originAreaExposureType"]'
ORIGIN_AREA_FIRST = 'select[ng-model="vm.viewData.originAreaInfo.firstSubOriginAreaType"]'
ORIGIN_AREA_SECOND = 'select[ng-model="vm.viewData.originAreaInfo.secondSubOriginAreaType"]'
ORIGIN_AREA_PLURAL = 'input[ng-model="vm.viewData.originAreaInfo.plural"]'  # 복수 원산지 체크
ORIGIN_IMPORTER = 'input[ng-model="vm.viewData.originAreaInfo.importer"]'  # 수입사


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 15. 사이즈
# ══════════════════════════════════════════════════════════════════════════════

SIZE_ON = 'input[ng-model="vm.isSizeOn"][value="true"]'
SIZE_OFF = 'input[ng-model="vm.isSizeOn"][value="false"]'


# 실측 확인 (2026-08-15)
PURCHASE_MIN_QTY = 'input[ng-model="vm.product.detailAttribute.purchaseQuantityInfo.minPurchaseQuantity"]'
PURCHASE_MAX_PER_ORDER = 'input[ng-model="vm.viewData.isUseMaxPurchaseQuantityPerOrder"]'
PURCHASE_MAX_PER_ID = 'input[ng-model="vm.viewData.isUseMaxPurchaseQuantityPerId"]'
TAX_TYPE_RADIO = 'input[ng-model="vm.product.detailAttribute.taxType"]'
VIDEO_TITLE = 'input[ng-model="vm.product.videos[0].title"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 17. 검색설정 (키워드 태그)
# ══════════════════════════════════════════════════════════════════════════════

SEARCH_KEYWORD_INPUT = [
    'input[ng-model="vm.searchKeyword"]',
    'input[placeholder*="키워드"]',
    'input[placeholder*="태그"]',
]

# ⚠ 2026-08-15 실측: vm.isSearchTagOn 은 존재하지 않는다(구버전 잔재).
#   검색설정 섹션은 on/off 라디오가 아니라 태그 입력창 + SEO 필드로 구성된다.
SEARCH_KEYWORD_ON = 'input[ng-model="vm.isSearchTagOn"][value="true"]'  # deprecated
SEARCH_KEYWORD_OFF = 'input[ng-model="vm.isSearchTagOn"][value="false"]'  # deprecated

# 실측 확인된 검색설정 필드 (2026-08-15)
# ⚠ SEARCH_TAG_INPUT 은 태그 입력이 아니었다(2026-08-15 재실측).
#   vm.searchKeyword 는 maxItems=1 인 **브랜드/제조사 자동완성**이다.
#   이걸 태그로 알고 조작해서 다섯 번 헛짚었다.
#   태그 조작은 scripts.naver.smartstore.product.tag_section.TagSection 을 쓴다.
SEARCH_TAG_INPUT_DEPRECATED = 'input[ng-model="vm.searchKeyword"]'  # 쓰지 말 것 — 브랜드/제조사

# 태그 위젯 본체는 <select> 이고 config 로 특정한다.
# 전제조건: '검색설정' 섹션 펼침 + SEARCH_TAG_DIRECT_CHECKBOX 체크(ng-if)
SEARCH_TAG_WIDGET_CONFIG = "::vm.config.directInputSelectizeConfig"
SEARCH_TAG_DIRECT_CHECKBOX = 'input[ng-model="vm.viewData.isDirectInput"]'
SEARCH_TAG_VALUE = 'input[ng-model="vm.product.detailAttribute.seoInfo.sellerTags"]'
# 등록된 태그가 렌더링되는 곳 (.selectize-input .item 이 아니다)
SEARCH_TAG_CHIPS = ".choice-tag .choice-label strong"

SEO_PAGE_TITLE = 'input[ng-model="vm.product.detailAttribute.seoInfo.pageTitle"]'
SEO_META_DESCRIPTION = 'input[ng-model="vm.product.detailAttribute.seoInfo.metaDescription"]'


# ══════════════════════════════════════════════════════════════════════════════
# 섹션 18. 노출채널
# ══════════════════════════════════════════════════════════════════════════════

CHANNEL_SMARTSTORE = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].channelServiceType"]'
CHANNEL_NAVER_SHOP = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].epInfo.naverShoppingRegistration"]'
CHANNEL_DISPLAY_ON = (
    'input[ng-model="vm.singleChannelProductMap[channelServiceType].channelProductDisplayStatusType"][value="ON"]'
)
CHANNEL_DISPLAY_OFF = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].channelProductDisplayStatusType"][value="SUSPENSION"]'
CHANNEL_EXCLUSIVE = 'input[ng-model="vm.singleChannelProductMap[channelServiceType].storeKeepExclusiveProduct"]'


# ══════════════════════════════════════════════════════════════════════════════
# 저장 버튼
# ══════════════════════════════════════════════════════════════════════════════

BTN_SAVE = ['button:has-text("저장하기")']
BTN_TEMP_SAVE = ['button:has-text("임시저장")']
BTN_PREVIEW = ['button:has-text("미리보기")']
BTN_CANCEL = ['button:has-text("취소")']


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
