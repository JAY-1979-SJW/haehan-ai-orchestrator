/** 하나팩스 API 호출 — 공용 프록시(/api/proxy)로 /api/v1/hanafax/* 를 부른다. */
const BASE = "/api/proxy/api/v1/hanafax";

export interface Recipient {
  fax: string;
  name: string;
}

export interface Authorization {
  id: string;
  name: string;
  subject: string;
  document_ref: string;
  document_name?: string;
  document_matches?: boolean;
  draft_expired?: boolean;
  pending_numbers?: string[];
  recipients?: Recipient[];
  recipient_count: number;
  approved: boolean;
  revoked: boolean;
  live: boolean;
  approved_by?: string | null;
  max_per_run: number;
  max_per_day: number;
  max_total: number;
  allowed_start: string;
  allowed_end: string;
  created_by?: string | null;
  created_at: string;
}

export interface LogRow {
  fax_digits: string;
  status: string;
  job_id: string | null;
  message: string;
  created_at: string;
}

export interface RunStatus {
  running: boolean;
  last: { status: string; message: string; finished_at: string } | null;
}

export interface PreviewStatus {
  running: boolean;
  state: { ok: boolean; message: string; shown?: number; total?: number; missing?: string[]; finished_at: string } | null;
  image_ready: boolean;
}

export interface ReconcileStatus {
  running: boolean;
  state: {
    ok: boolean;
    message?: string;
    checked?: number;
    delivered?: number;
    delivery_failed?: number;
    partial?: number;
    unmatched?: number;
    finished_at: string;
  } | null;
}

export interface AddressGroup {
  name: string;
  intid: string;
  members: number;
  fax_count: number;
}

export interface GroupSyncStatus {
  running: boolean;
  cached: boolean;
  state: { ok: boolean | null; page?: number; pages?: number; members?: number; message?: string } | null;
}

export interface CreateInput {
  name: string;
  subject: string;
  document_ref: string;
  recipients: Recipient[];
  site_group?: string;
  group_offset?: number;
  group_limit?: number;
  max_per_run?: number;
  max_per_day?: number;
  allowed_start: string;
  allowed_end: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* JSON 이 아니면 상태 코드만 */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

const post = <T,>(path: string, body: unknown = {}) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const faxApi = {
  list: () => call<Authorization[]>("authorizations"),
  get: (id: string) => call<Authorization>(`authorizations/${id}`),
  create: (input: CreateInput) => post<Authorization>("authorizations", input),
  approve: (id: string, live: boolean, startNow: boolean, pin: string) =>
    post<Authorization>(`authorizations/${id}/approve`, { confirmed: true, live, start_now: startNow, pin }),
  pinStatus: () => call<{ configured: boolean; locked_until: string | null }>("approval-pin"),
  setPin: (pin: string, oldPin = "") => post<{ configured: boolean }>("approval-pin", { pin, old_pin: oldPin }),
  revoke: (id: string) => post<Authorization>(`authorizations/${id}/revoke`),
  run: (id: string) => post<RunStatus>(`authorizations/${id}/run`),
  runStatus: (id: string) => call<RunStatus>(`authorizations/${id}/run`),
  resolvePending: (id: string, fax: string, outcome: "sent" | "not_sent", pin: string) =>
    post<Authorization>(`authorizations/${id}/resolve`, { fax, outcome, pin }),
  addressGroups: () => call<AddressGroup[]>("address-groups"),
  startGroupSync: (intid: string) => post<GroupSyncStatus>(`address-groups/${intid}/sync`),
  groupSyncStatus: (intid: string) => call<GroupSyncStatus>(`address-groups/${intid}/sync`),
  startReconcile: (id: string) => post<ReconcileStatus>(`authorizations/${id}/reconcile`),
  reconcileStatus: (id: string) => call<ReconcileStatus>(`authorizations/${id}/reconcile`),
  startPreview: (id: string) => post<PreviewStatus>(`authorizations/${id}/preview`),
  previewStatus: (id: string) => call<PreviewStatus>(`authorizations/${id}/preview`),
  previewImageUrl: (id: string, stamp: string) => `${BASE}/authorizations/${id}/preview.png?t=${encodeURIComponent(stamp)}`,
  log: (id: string) => call<LogRow[]>(`authorizations/${id}/log`),
  killSwitch: () => call<{ kill_switch: boolean }>("kill-switch"),
  setKillSwitch: (on: boolean, pin = "") => post<{ kill_switch: boolean }>("kill-switch", { on, pin }),
};

/** "번호, 이름" 한 줄씩 → 수신자 목록 */
export function parseRecipients(text: string): Recipient[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [fax, ...rest] = line.split(/[,\t]/);
      return { fax: fax.trim(), name: rest.join(" ").trim() };
    });
}
