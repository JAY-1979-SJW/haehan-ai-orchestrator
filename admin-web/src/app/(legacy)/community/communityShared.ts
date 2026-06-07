/** 커뮤니티 레이더 공유 — 타입·헬퍼 (섹션 모듈 공용) */

export interface Site { id: string; name: string; url: string; note?: string; added_at?: string }
export interface Opportunity { idea: string; why?: string }
export interface Topic { name: string; share?: string }
export interface Report {
  ok: boolean; error?: string; analyzed_count?: number;
  summary?: string; trends?: string[]; opportunities?: Opportunity[];
  topics?: Topic[]; actions?: string[]; source_method?: string; site?: string;
}

export function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t = window.localStorage.getItem("haehan_ai_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export const J = { "Content-Type": "application/json" };
