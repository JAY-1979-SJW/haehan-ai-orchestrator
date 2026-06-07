/** 리뷰/문의 — 문의 유형·자동답변 템플릿 데이터 */

export const INQUIRY_TYPES = [
  { type: "배송 문의",  desc: "배송 예정일, 운송장 조회 등", sla: "12시간 내" },
  { type: "상품 문의",  desc: "스펙, 재질, 사용법 등",       sla: "24시간 내" },
  { type: "환불 문의",  desc: "교환/반품/취소 요청",         sla: "24시간 내" },
];

export const AUTO_TEMPLATES = [
  { label: "5점 리뷰",       template: "소중한 리뷰 감사드립니다! 항상 최선을 다하겠습니다." },
  { label: "4점 리뷰",       template: "리뷰 감사드립니다. 더 나은 서비스를 위해 노력하겠습니다." },
  { label: "3점 이하 리뷰",  template: "불편을 드려 죄송합니다. 문의사항은 채팅으로 연락 부탁드립니다." },
];

