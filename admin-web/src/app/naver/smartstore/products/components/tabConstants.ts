export type Tab = "list" | "register" | "bulk" | "desc" | "auto" | "edit";

export const TABS: { id: Tab; label: string }[] = [
  { id: "list",     label: "상품 목록" },
  { id: "register", label: "상품 등록" },
  { id: "bulk",     label: "일괄 등록" },
  { id: "desc",     label: "상세설명 빌더" },
  { id: "auto",     label: "자동 등록" },
  { id: "edit",     label: "상품 수정" },
];

export const REGISTER_STEPS = [
  { step: 1, title: "카테고리 선택", desc: "정확한 카테고리 선택 (판매 수수료 결정)", required: true },
  { step: 2, title: "기본 정보",     desc: "상품명(최대 100자), 판매가(최소 10원), 재고 수량", required: true },
  { step: 3, title: "이미지 등록",   desc: "대표이미지 필수(최대 10MB), 추가이미지 선택", required: true },
  { step: 4, title: "상세 설명",     desc: "스마트에디터 또는 HTML 직접 작성", required: false },
  { step: 5, title: "저장 및 노출",  desc: "임시저장 → 최종 저장 → 노출 설정 확인", required: true },
];
