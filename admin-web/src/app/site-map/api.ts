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

export interface DataSource {
  host: string;
  path: string;
  query_keys: string[];
  top_keys: string[];
  lists: { path: string; count: number; fields: string[] }[];
  seen: number;
}

export interface DeclaredTool {
  name: string;
  description: string;
  kind: "declarative" | "imperative";
  fields: string[];
  required: string[];
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
  /** 메뉴 색인(M8)·관측한 서로 다른 주소 총수(M9, 상한 때문에 잘렸는지) */
  menu?: { label: string; href: string }[];
  menu_total_seen?: number;
  /** 화면이 로드될 때 사이트가 부르는 데이터 API 의 구조(M9, 값 없음) */
  data_sources?: DataSource[];
  /** 사이트가 선언한 에이전트용 도구(WebMCP, 읽기만) */
  declared_tools?: DeclaredTool[];
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

// ── 등록 사이트(M7-S1) — /api/v1/site-registry/* (관리자 전용). 기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md
const REGISTRY = "/api/proxy/api/v1/site-registry";

export type SiteState = "registered" | "exploring" | "ready" | "incomplete" | "needs_login" | "blocked" | "deregistered";
export const SITE_STATE_LABEL: Record<SiteState, string> = {
  registered: "등록됨(탐색 전)",
  exploring: "탐색 중",
  ready: "사용 가능",
  incomplete: "탐색 불완전(업무 0건)",
  needs_login: "로그인 필요",
  blocked: "차단됨(확인 필요)",
  deregistered: "해제됨",
};

export interface RegisteredSite {
  host: string;
  state: SiteState;
  policy: { auto_explore: string; daily_explore_max: number; max_pages: number };
  registered_by: string;
  registered_at: string;
  last_explored_at: string;
  /** 사이트가 다른 호스트로 넘긴 경우 실제로 탐색한 호스트 */
  explored_host?: string;
  note: string;
  map: { tasks: number; verified: number; stale: number; auth: Auth };
  explored?: { host: string; tasks: number; verified: number; stale: number; auth: Auth };
}

export interface OfficialApiAdvice {
  checked: boolean;
  found?: boolean;
  advice?: string;
  error?: string;
  vendors?: { name: string; status: string; docs: string; cost: string }[];
}

export interface RegisterResult {
  site: RegisteredSite;
  official_api: OfficialApiAdvice;
}

async function registryCall<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`${REGISTRY}${path}`, {
    method,
    cache: "no-store",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

export const siteRegistryApi = {
  list: () => registryCall<{ items: RegisteredSite[] }>("").then((r) => r.items),
  register: (host: string, auth: Auth) => registryCall<RegisterResult>("", "POST", { host, auth }),
  deregister: (host: string) => registryCall<RegisteredSite>(`/${encodeURIComponent(host)}/deregister`, "POST"),
};
