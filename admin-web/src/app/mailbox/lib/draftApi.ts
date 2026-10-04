/**
 * 메일 AI 초안 API — 공용 프록시로 /api/v1/naver-mailbox/drafts* · /instructions 를 부른다.
 * 기준서: docs/specs/2026-10-02_mailbox_ai_window.md
 * 보내기(`send`)는 사람이 카드 버튼으로만 호출한다(AI 허용 API 목록에 없다).
 */
const BASE = "/api/proxy/api/v1/naver-mailbox";

export type DraftStatus = "pending" | "sending" | "sent" | "failed" | "unknown" | "cancelled" | "expired";

export interface Draft {
  id: string;
  account: string;
  status: DraftStatus;
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  body_preview: string;
  rich: boolean;
  attachments: { name: string; size: number; kind: string }[];
  in_reply_to: string;
  created_by: string;
  created_at: string;
  expires_at: string;
  sent_at: string | null;
  approved_by: string | null;
  result: { ok?: boolean; error?: string; message?: string; recipient_count?: number; refused_count?: number };
}

async function failure(res: Response): Promise<Error> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") detail = body.detail;
  } catch {
    /* JSON 이 아니면 상태 코드만 보여 준다 */
  }
  return new Error(detail);
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, { cache: "no-store" });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

export const draftApi = {
  list: (account: string, all = false) =>
    getJson<{ drafts: Draft[] }>(`drafts?account=${encodeURIComponent(account)}${all ? "&all=true" : ""}`).then((r) => r.drafts),
  get: (id: string) => getJson<Draft>(`drafts/${id}`),
  /** 사람이 카드의 '승인하고 보내기'를 눌렀을 때만 */
  send: (id: string) => postJson<Draft>(`drafts/${id}/send`),
  cancel: (id: string) => postJson<Draft>(`drafts/${id}/cancel`),
  instructions: (account: string) => getJson<{ text: string }>(`instructions?account=${encodeURIComponent(account)}`).then((r) => r.text),
  saveInstructions: (account: string, text: string) => postJson<{ text: string }>("instructions", { account, text }).then((r) => r.text),
};

export const INSTRUCTIONS_MAX = 4000;
