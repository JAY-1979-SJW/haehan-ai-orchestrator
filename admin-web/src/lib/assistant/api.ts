/**
 * 비서앱 MVP read-only API client — APP_UI_SHELL_READONLY_API_WIRING_01
 * 보강: APP_UI_READONLY_BACKEND_STATUS_CARDS_01
 *
 * GET 전용 — POST/PUT/PATCH/DELETE 함수 없음
 * mutation 연결 금지: tasks 실행/approve/reject/execute 없음
 */
import type { ApiConnectionMeta, ErrorKind } from "@/types/assistant";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ApiState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T; meta: ApiConnectionMeta }
  | { status: "empty"; meta: ApiConnectionMeta }
  | { status: "error"; message: string; meta: ApiConnectionMeta }
  | { status: "mock_fallback"; data: T; meta: ApiConnectionMeta };

export function makeMeta(
  source: ApiConnectionMeta["source"],
  error_kind: ErrorKind = null,
): ApiConnectionMeta {
  return {
    source,
    last_checked: new Date().toISOString(),
    error_kind,
    is_read_only: true,
    mutation_allowed: false,
  };
}

export interface HealthResponse {
  status: string;
  service?: string;
  version?: string;
  dry_run_gate_enabled?: boolean;
}

export interface InboxItem {
  id: string;
  subject?: string;
  from?: string;
  received_at?: string;
  category?: string;
  read?: boolean;
}

export interface InboxResponse {
  items: InboxItem[];
  total: number;
}

async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    signal,
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

/** GET /api/v1/health */
export async function getAssistantHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  return getJson<HealthResponse>("/api/v1/health", signal);
}

/** GET /api/v1/inbox */
export async function getAssistantInbox(
  signal?: AbortSignal,
): Promise<InboxResponse> {
  return getJson<InboxResponse>("/api/v1/inbox", signal);
}
