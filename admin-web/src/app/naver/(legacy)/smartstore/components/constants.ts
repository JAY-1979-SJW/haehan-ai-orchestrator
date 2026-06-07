// ── 빠른 버튼 그룹 ───────────────────────────────────────────────────────────
export const QUICK_GROUPS = [
  {
    label: "조회",
    color: "#1D4ED8",
    bg: "#EFF6FF",
    border: "#BFDBFE",
    actions: [
      { label: "상품 목록",  prompt: "상품 목록을 보여줘" },
      { label: "주문 확인",  prompt: "최근 주문 목록을 확인해줘" },
      { label: "정산 조회",  prompt: "정산 내역을 조회해줘" },
      { label: "리뷰 확인",  prompt: "최근 리뷰와 문의를 확인해줘" },
      { label: "통계 조회",  prompt: "데이터 분석 통계를 조회해줘" },
    ],
  },
  {
    label: "실시간 수집",
    color: "#7C3AED",
    bg: "#F5F3FF",
    border: "#DDD6FE",
    actions: [
      { label: "상품 수집",  prompt: "CDP로 상품 목록을 실시간 수집해줘" },
      { label: "주문 수집",  prompt: "CDP로 주문 목록을 실시간 수집해줘" },
      { label: "정산 수집",  prompt: "CDP로 정산 내역을 실시간 수집해줘" },
      { label: "리뷰 수집",  prompt: "CDP로 리뷰와 문의를 실시간 수집해줘" },
      { label: "통계 수집",  prompt: "CDP로 데이터 분석 통계를 실시간 수집해줘" },
    ],
  },
  {
    label: "화면 이동",
    color: "#16A34A",
    bg: "#F0FDF4",
    border: "#BBF7D0",
    actions: [
      { label: "셀러센터 대시보드", prompt: "셀러센터 대시보드를 열어줘" },
      { label: "상품 등록 화면",    prompt: "셀러센터 상품 등록 페이지를 열어줘" },
      { label: "주문 화면",         prompt: "셀러센터 주문 페이지를 열어줘" },
      { label: "정산 화면",         prompt: "셀러센터 정산 페이지를 열어줘" },
      { label: "리뷰 화면",         prompt: "셀러센터 리뷰 페이지를 열어줘" },
    ],
  },
];

// ── 예시 칩 ──────────────────────────────────────────────────────────────────
export const EXAMPLE_CHIPS = [
  { label: "상품 목록",     prompt: "상품 목록을 보여줘" },
  { label: "주문 확인",     prompt: "최근 주문 목록을 확인해줘" },
  { label: "정산 조회",     prompt: "정산 내역을 조회해줘" },
  { label: "리뷰 확인",     prompt: "최근 리뷰와 문의를 확인해줘" },
  { label: "상품 수집",     prompt: "CDP로 상품 목록을 실시간 수집해줘" },
  { label: "셀러센터 열기", prompt: "셀러센터 상품 목록 페이지를 열어줘" },
  { label: "통계 수집",     prompt: "데이터 분석 통계를 수집해줘" },
];

// ── 리스크 배지 ───────────────────────────────────────────────────────────────
export const RISK_BADGE: Record<string, string> = {
  read:    "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  prepare: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
  submit:  "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
};

// ── 상태 배지 ────────────────────────────────────────────────────────────────
export const STATUS_BADGE: Record<string, string> = {
  planned:     "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]",
  in_progress: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  done:        "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
};

// ── 메뉴 카드 타입 ────────────────────────────────────────────────────────────
export interface MenuItem {
  key: string;
  label: string;
  features: string[];
  locked?: boolean;
}

// ── 메뉴 카드 색상 ────────────────────────────────────────────────────────────
export const MENU_CARD_COLOR: Record<string, string> = {
  dashboard:   "border-[#BFDBFE] bg-[#EFF6FF] text-[#1D4ED8]",
  products:    "border-[#BBF7D0] bg-[#F0FDF4] text-[#16A34A]",
  orders:      "border-[#FED7AA] bg-[#FFF7ED] text-[#C2410C]",
  settlements: "border-[#DDD6FE] bg-[#F5F3FF] text-[#7C3AED]",
  reviews:     "border-[#FECACA] bg-[#FEF2F2] text-[#DC2626]",
  stats:       "border-[#E5E7EB] bg-[#F9FAFB] text-[#374151]",
  marketing:   "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]",
  store_info:  "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]",
};

// ── 정적 메뉴 목록 (13개) ─────────────────────────────────────────────────────
export const STATIC_MENUS: MenuItem[] = [
  { key: "dashboard",   label: "대시보드",      features: ["판매 현황", "미처리 주문", "정산 예정액"] },
  { key: "products",    label: "상품 관리",      features: ["상품 등록", "상품 목록", "카테고리 관리"] },
  { key: "orders",      label: "주문 관리",      features: ["신규 주문", "발송 처리", "취소/교환/반품"] },
  { key: "settlements", label: "정산 관리",      features: ["정산 내역", "세금계산서", "매출 통계"] },
  { key: "reviews",     label: "리뷰·문의",      features: ["상품 리뷰", "고객 문의", "답변 관리"] },
  { key: "stats",       label: "데이터 분석",    features: ["방문자 통계", "검색 키워드", "판매 분석"] },
  { key: "marketing",   label: "마케팅",         features: ["쿠폰", "포인트", "기획전"], locked: true },
  { key: "store_info",  label: "스토어 정보",    features: ["기본 정보", "배송 정책", "반품 정책"] },
];

// ── 상품 등록 5단계 ───────────────────────────────────────────────────────────
export const REGISTER_STEPS = [
  { step: 1, title: "카테고리 선택", desc: "정확한 카테고리 선택 (판매 수수료 결정)", required: true },
  { step: 2, title: "기본 정보",     desc: "상품명(최대 100자), 판매가(최소 10원), 재고 수량", required: true },
  { step: 3, title: "이미지 등록",   desc: "대표이미지 필수(최대 10MB), 추가이미지 선택", required: true },
  { step: 4, title: "상세 설명",     desc: "스마트에디터 또는 HTML 직접 작성", required: false },
  { step: 5, title: "저장 및 노출",  desc: "임시저장 → 최종 저장 → 노출 설정 확인", required: true },
];

export const TOOL_LABEL: Record<string, string> = {
  list_products:      "상품 목록 조회",
  collect_products:   "상품 목록 수집",
  list_orders:        "주문 목록 조회",
  collect_orders:     "주문 목록 수집",
  list_settlements:   "정산 내역 조회",
  collect_settlements:"정산 내역 수집",
  list_reviews:       "리뷰/문의 조회",
  collect_reviews:    "리뷰/문의 수집",
  list_stats:         "통계 조회",
  collect_stats:      "통계 수집",
  register_product:   "상품 등록",
  edit_product:       "상품 수정",
  open_seller_center: "셀러센터 이동",
};
