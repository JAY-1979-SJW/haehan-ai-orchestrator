/** 메일함 — 공유 라벨·타입 */

export const SOURCE_LABEL: Record<string, string> = {
  telegram_command: "텔레그램",
  email: "이메일",
  gmail: "Gmail",
  naver_mail: "네이버",
  hiworks: "하이웍스",
  manual: "수동",
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
