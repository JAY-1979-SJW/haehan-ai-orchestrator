/** 카페 탭 공유 — 타입·상수·헬퍼 (탭 모듈 공용) */

export type Tab = "summary" | "my-cafes" | "articles" | "ai" | "report";

export const CATEGORIES = [
  "노무", "계약·하도급", "공사관리", "세무·회계", "법규·인허가",
  "안전", "행정·서류", "장비·자재", "커뮤니티", "기타",
];

export const CAT_COLOR: Record<string, string> = {
  "노무": "bg-blue-50 text-blue-700 border-blue-200",
  "세무·회계": "bg-green-50 text-green-700 border-green-200",
  "계약·하도급": "bg-purple-50 text-purple-700 border-purple-200",
  "공사관리": "bg-orange-50 text-orange-700 border-orange-200",
  "법규·인허가": "bg-red-50 text-red-700 border-red-200",
  "안전": "bg-yellow-50 text-yellow-700 border-yellow-200",
  "행정·서류": "bg-indigo-50 text-indigo-700 border-indigo-200",
  "장비·자재": "bg-teal-50 text-teal-700 border-teal-200",
  "커뮤니티": "bg-pink-50 text-pink-700 border-pink-200",
  "기타": "bg-gray-50 text-gray-600 border-gray-200",
};

export type AiReport = {
  ok: boolean; summary: string; trends: string[];
  opportunities: { idea: string; why: string }[];
  topics: { name: string; share: string }[];
  actions: string[]; post_count: number; total_collected: number;
};

/** 프록시 경유 POST (토큰 자동 첨부) */
export async function apiPost(path: string, body: unknown) {
  const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
  const r = await fetch(`/api/proxy${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
    body: JSON.stringify(body),
  });
  return r.json();
}

export function confidenceBadge(c: string): string {
  return (({
    high: "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
    medium: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
    low: "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
  } as Record<string, string>)[c]) ?? "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]";
}
