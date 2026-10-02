/**
 * 메일 순차 대량 발송 API — 공용 프록시(/api/proxy)로 /api/v1/mail-bulk/* 를 부른다.
 * 기준서: docs/specs/2026-10-02_mail_bulk_sequential.md (관리자 전용, AI 는 이 API 를 쓰지 못한다)
 */
const BASE = "/api/proxy/api/v1/mail-bulk";

export type BulkKind = "transaction" | "promo";

export interface BulkRecipient {
  email: string;
  name: string;
  company: string;
}

export interface BulkAuthorization {
  id: string;
  name: string;
  account: string;
  kind: BulkKind;
  subject: string;
  body_preview: string;
  recipient_count: number;
  recipients_preview: BulkRecipient[];
  attachments: { name: string; size: number }[];
  approved: boolean;
  revoked: boolean;
  paused: boolean;
  paused_reason: string;
  live: boolean;
  test_sent_at: string | null;
  approved_by: string | null;
  interval_sec: number;
  max_per_run: number;
  max_per_day: number;
  max_total: number;
  allowed_start: string;
  allowed_end: string;
  created_at: string;
}

export interface BulkStatus {
  running: boolean;
  last: { status: string; message?: string; finished_at: string; summary?: BulkRunSummary } | null;
  counts: Record<string, number>;
  remaining: number;
  paused: boolean;
  paused_reason: string;
  kill_switch: boolean;
}

export interface BulkRunSummary {
  decision: string;
  reason: string;
  dry_run: boolean;
  sent: number;
  failed: number;
  unknown: number;
  stopped_midway: boolean;
  paused_reason: string;
}

export interface BulkLogRow {
  email: string;
  status: string;
  message: string;
  created_at: string;
}

export interface BulkImportResult {
  recipients: { email: string; name: string; company: string }[];
  stats: { rows: number; invalid: number; duplicate: number; opted_out: number; usable: number };
}

export interface BulkCreateInput {
  account: string;
  name: string;
  kind: BulkKind;
  subject: string;
  body: string;
  recipients: { email: string; name: string; company: string }[];
  attachment_paths: string[];
  interval_sec: number;
  max_per_day: number;
  allowed_start: string;
  allowed_end: string;
}

async function failure(res: Response): Promise<Error> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") detail = body.detail;
  } catch {
    /* 본문이 JSON 이 아니면 상태 코드만 보여 준다 */
  }
  return new Error(detail);
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, { cache: "no-store" });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

export const bulkApi = {
  list: () => getJson<{ items: BulkAuthorization[] }>("authorizations").then((r) => r.items),
  get: (id: string) => getJson<{ authorization: BulkAuthorization; status: BulkStatus }>(`authorizations/${id}`),
  log: (id: string) => getJson<{ items: BulkLogRow[] }>(`authorizations/${id}/log`).then((r) => r.items),
  create: (input: BulkCreateInput) => postJson<BulkAuthorization>("authorizations", input),
  selfTest: (id: string, to: string) => postJson<{ ok: boolean; to: string }>(`authorizations/${id}/self-test`, { to }),
  approve: (id: string, live: boolean) => postJson<BulkAuthorization>(`authorizations/${id}/approve`, { live }),
  revoke: (id: string) => postJson<BulkAuthorization>(`authorizations/${id}/revoke`),
  pause: (id: string) => postJson<BulkAuthorization>(`authorizations/${id}/pause`),
  resume: (id: string) => postJson<BulkAuthorization>(`authorizations/${id}/resume`),
  run: (id: string) => postJson<BulkStatus>(`authorizations/${id}/run`),
  importFile: (path: string) => postJson<BulkImportResult>("import", { path }),
  optOut: (email: string, reason: string) => postJson<{ email: string }>("opt-out", { email, reason }),
  killSwitch: (on: boolean) => postJson<{ kill_switch: boolean }>("kill-switch", { on }),
};

/** 승인 전 확인 창에 보여 줄 예상 소요(하루 상한·간격 기준). */
export function estimate(count: number, perDay: number, intervalSec: number): { days: number; minutesPerDay: number } {
  const perDayEffective = Math.max(1, Math.min(perDay, count));
  return { days: Math.ceil(count / Math.max(1, perDay)), minutesPerDay: Math.ceil((perDayEffective * intervalSec) / 60) };
}

export const STATUS_LABEL: Record<string, string> = {
  sent: "보냄",
  failed: "실패",
  unknown: "확인 필요",
  dry_run: "드라이런",
};

export function stateOf(a: BulkAuthorization): { label: string; tone: "gray" | "blue" | "green" | "orange" | "red" } {
  if (a.revoked) return { label: "취소됨", tone: "red" };
  if (a.paused) return { label: "멈춤", tone: "orange" };
  if (!a.approved) return { label: a.test_sent_at ? "승인 대기" : "시험 발송 필요", tone: "gray" };
  return a.live ? { label: "실전송 승인", tone: "green" } : { label: "드라이런 승인", tone: "blue" };
}

export const PAUSE_REASON: Record<string, string> = {
  auth_failed: "로그인이 거부되었습니다. 앱 비밀번호·IMAP/SMTP 설정을 확인하세요.",
  limit_or_block: "발송 한도 또는 차단 응답을 받았습니다. 하루 상한을 낮추거나 시간을 두고 재개하세요.",
  consecutive_failures: "연속으로 3번 실패했습니다. 네트워크·서버 상태를 확인하세요.",
  unknown_result: "마지막 메일이 서버에 전달됐는지 확인하지 못했습니다. 보낸메일함을 확인하세요(이 주소는 다시 보내지 않습니다).",
  manual: "사용자가 멈췄습니다.",
};
