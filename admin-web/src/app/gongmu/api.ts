/**
 * 공무 업무판 API — 공용 프록시(/api/proxy)로 /api/v1/gongmu/* 를 부른다(관리자 전용).
 * 기준서: docs/specs/2026-10-02_construction_gongmu.md (G1)
 */
const BASE = "/api/proxy/api/v1/gongmu";

export type TaskStatus = "todo" | "doing" | "submit_wait" | "done" | "na";
export type Grade = "overdue" | "soon" | "later" | "unknown" | "closed";

export const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: "할 일",
  doing: "진행",
  submit_wait: "제출 대기",
  done: "완료",
  na: "해당 없음",
};
export const STATUS_ORDER: TaskStatus[] = ["todo", "doing", "submit_wait", "done", "na"];

export interface Site {
  id: string;
  name: string;
  client: string;
  location: string;
  start_date: string | null;
  end_date: string | null;
  role: "prime" | "sub";
  contract_amount: number | null;
  manager: string;
  memo: string;
}

export interface ContractChange {
  date: string;
  amount: number | null;
  period_end: string | null;
  memo: string;
}

export interface Contract {
  id: string;
  site_id: string;
  counterparty: string;
  kind: "prime" | "sub";
  amount: number | null;
  contract_date: string | null;
  changes: ContractChange[];
}

export interface Task {
  id: string;
  site_id: string;
  site_name: string;
  contract_id: string;
  catalog_code: string;
  catalog_name: string;
  category: "legal" | "practice";
  basis: string;
  verify_law: boolean;
  submit_to: string;
  period: string;
  due_date: string | null;
  status: TaskStatus;
  status_label: string;
  grade: Grade;
  days_left: number | null;
  assignee: string;
  memo: string;
  reason: string;
}

export interface TaskDoc {
  doc_name: string;
  ready: boolean;
  file_path: string;
  sha256: string;
}

export interface TaskDetail extends Task {
  missing_docs: string[];
  docs_checklist: TaskDoc[];
}

export interface Summary {
  counts: { overdue: number; soon: number; unknown: number; open: number };
  overdue: Task[];
  soon: Task[];
  unknown: Task[];
  disclaimer: string;
}

export interface ImportResult {
  imported: number;
  skipped_existing?: number;
  errors: { line: number; error: string }[];
}

export type Settings = Record<string, number>;

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

async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    method,
    cache: "no-store",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

export const gongmuApi = {
  summary: () => call<Summary>("summary"),
  settings: () => call<{ settings: Settings; disclaimer: string }>("settings"),
  saveSettings: (values: Settings) => call<{ settings: Settings }>("settings", "PUT", { values }),
  sites: () => call<{ items: Site[] }>("sites").then((r) => r.items),
  site: (id: string) => call<{ site: Site; contracts: Contract[] }>(`sites/${id}`),
  createSite: (input: Record<string, unknown>) => call<{ site: Site }>("sites", "POST", input),
  tasks: (siteId?: string) => call<{ items: Task[] }>(`tasks${siteId ? `?site_id=${siteId}` : ""}`).then((r) => r.items),
  task: (id: string) => call<TaskDetail>(`tasks/${id}`),
  setStatus: (id: string, status: TaskStatus) => call<TaskDetail>(`tasks/${id}/status`, "POST", { status }),
  patchTask: (id: string, body: { due_date?: string | null; assignee?: string; memo?: string }) =>
    call<TaskDetail>(`tasks/${id}`, "PATCH", body),
  setDoc: (id: string, doc_name: string, ready: boolean, path: string) =>
    call<TaskDetail>(`tasks/${id}/docs`, "POST", { doc_name, ready, path }),
  createContract: (siteId: string, input: Record<string, unknown>) => call<{ contract: Contract }>(`sites/${siteId}/contracts`, "POST", input),
  addChange: (contractId: string, input: Record<string, unknown>) => call<{ contract: Contract }>(`contracts/${contractId}/changes`, "POST", input),
  importSites: (path: string) => call<ImportResult>("import/sites", "POST", { path }),
  importContracts: (path: string) => call<ImportResult>("import/contracts", "POST", { path }),
};
