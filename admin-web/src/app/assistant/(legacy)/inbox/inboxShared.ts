/** 메일함 — 공유 라벨·타입 */

export const SOURCE_LABEL: Record<string, string> = {
  telegram_command: "텔레그램",
  email: "이메일",
  gmail: "Gmail",
  naver_mail: "네이버",
  hiworks: "하이웍스",
  manual: "수동",
  kakaotalk_channel: "카카오톡",
  kakaowork: "카카오워크",
};

export const CATEGORY_LABEL: Record<string, string> = {
  support: "문의",
  sales: "영업/견적",
  bidding: "입찰/조달",
  accounting: "정산/청구",
  development: "개발/기술",
  operations: "운영/장애",
  general: "일반",
};

export const STATUS_STYLE: Record<string, string> = {
  new: "bg-blue-50 text-blue-700 border-blue-200",
  reviewed: "bg-yellow-50 text-yellow-700 border-yellow-200",
  task_created: "bg-green-50 text-green-700 border-green-200",
  archived: "bg-gray-50 text-gray-500 border-gray-200",
};

export const STATUS_LABEL: Record<string, string> = {
  new: "신규",
  reviewed: "검토됨",
  task_created: "작업생성",
  archived: "보관",
};

export function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}분 전`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}시간 전`;
    return `${Math.floor(h / 24)}일 전`;
  } catch {
    return iso?.slice(0, 10) ?? "-";
  }
}

export type ComposeStep = "form" | "preview" | "done" | "error";
