/**
 * 사이트 업무 지도 API — 공용 프록시(/api/proxy)로 /api/v1/site-map/* 를 부른다(관리자 전용).
 * 기준서: docs/specs/2026-10-03_site_task_map.md (M4)
 */
const BASE = "/api/proxy/api/v1/site-map";

export type Risk = "read" | "write" | "submit";
export type TaskState = "observed" | "verified" | "stale";
export type Auth = "public" | "login" | "certificate";

export const RISK_LABEL: Record<Risk, string> = { read: "조회", write: "입력·저장", submit: "제출·신고·삭제" };
export const STATE_LABEL: Record<TaskState, string> = { observed: "관찰됨", verified: "검증됨", stale: "재확인 필요" };
export const AUTH_LABEL: Record<Auth, string> = { public: "공개", login: "로그인", certificate: "인증서" };
export const CATEGORIES = ["search", "input", "submit", "login", "navigate", "download", "unclassified"] as const;
export type Category = (typeof CATEGORIES)[number];
export const CATEGORY_LABEL: Record<Category, string> = {
  search: "조회·검색",
  input: "입력",
  submit: "제출",
  login: "로그인",
  navigate: "이동",
  download: "다운로드",
  unclassified: "분류 미정",
};

export interface MapField {
  name: string;
  id: string;
  type: string;
  role: string;
  label: string;
  required: boolean;
}

export interface RecorderStep {
  type: string;
  url?: string;
  value?: string;
  selectors?: string[][];
}

export interface MapTask {
  id: string;
  name: string;
  category: Category;
  purpose: string;
  risk: Risk;
  auth: Auth;
  state: TaskState;
  url: string;
  host: string;
  fields: MapField[];
  control: string;
  outputs: string[];
  steps: RecorderStep[];
  fingerprint: string;
  observed_at: string;
  verified_at: string;
  failures: number;
  changes: { at: string; from: string; to: string; was: string }[];
}

export interface HostSummary {
  host: string;
  auth?: Auth;
  tasks?: number;
  verified?: number;
  stale?: number;
  updated_at?: string;
  error?: string;
}

export interface SiteMap {
  version: number;
  host: string;
  auth: Auth;
  updated_at: string;
  tasks: MapTask[];
  /** 탐색했다는 사실과 점검표(업무가 0건이어도 남는다) */
  explored?: { at: string; pages: number; coverage?: { warning?: string; redirected_to?: string } };
}

export interface ResultTable {
  headers: string[];
  rows: string[][];
  truncated: boolean;
}

export interface RunResult {
  ok: boolean;
  task_id: string;
  state?: TaskState;
  url?: string;
  steps_done?: number;
  tables?: ResultTable[];
  error?: string;
  note?: string;
}

export interface ExploreRequestSummary {
  id: string;
  host: string;
  status: string;
  created_at: string;
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

export const siteMapApi = {
  hosts: () => call<{ items: HostSummary[] }>("hosts").then((r) => r.items),
  map: (host: string) => call<SiteMap>(encodeURIComponent(host)),
  classify: (host: string, input: { task_id: string; name?: string; purpose?: string; category?: Category }) =>
    call<MapTask>(`${encodeURIComponent(host)}/classify`, "POST", input),
  outcome: (host: string, taskId: string, ok: boolean) => call<MapTask>(`${encodeURIComponent(host)}/outcome`, "POST", { task_id: taskId, ok }),
  run: (host: string, taskId: string, params: Record<string, string>) =>
    call<RunResult>(`${encodeURIComponent(host)}/run`, "POST", { task_id: taskId, params }),
  exploreRequests: () => call<{ items: ExploreRequestSummary[] }>("explore/requests").then((r) => r.items),
};
