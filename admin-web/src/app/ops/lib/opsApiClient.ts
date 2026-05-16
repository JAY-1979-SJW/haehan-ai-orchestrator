/**
 * 운영센터 API 클라이언트.
 * 실제 백엔드 read-only API를 우선 호출하고, 실패 시 mock/fallback으로 복구.
 *
 * 금지: secret/token/password/session/cookie 노출
 * 금지: 실제 승인/거절 실행, 실제 위험 실행
 * 모든 함수: GET/read-only only
 */
import type {
  ApprovalItem,
  AuditEventRow,
  AgentStatus,
  WebTaskAction,
  DashboardMetric,
  IntegrationStatus,
} from "./types";
import {
  MOCK_APPROVAL_QUEUE,
  MOCK_AUDIT_EVENTS,
  MOCK_AGENT_STATUSES,
  MOCK_WEB_TASKS,
  MOCK_METRICS,
  MOCK_INTEGRATIONS,
} from "./mockOpsData";

const API_BASE = "/api/v1";
const TIMEOUT_MS = 5000;

type FetchSource = "live" | "fallback" | "error" | "static";

export interface OpsResult<T> {
  data: T;
  source: FetchSource;
  error?: string;
}

async function safeGet<T>(
  path: string,
  fallback: T,
  timeoutMs = TIMEOUT_MS,
): Promise<{ data: unknown; source: FetchSource; error?: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: "Bearer admin-token" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) {
      return { data: fallback, source: "fallback", error: `HTTP ${res.status}` };
    }
    const json = await res.json();
    return { data: json, source: (json?.source as FetchSource) ?? "live" };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { data: fallback, source: "fallback", error: msg };
  } finally {
    clearTimeout(timer);
  }
}

// ── 승인 대기 ────────────────────────────────────────────────────────────────

export async function fetchApprovalQueue(): Promise<OpsResult<ApprovalItem[]>> {
  const { data, source, error } = await safeGet("/ops/approvals", null);
  if (source === "live" || source === "static") {
    const items = (data as { items?: ApprovalItem[] })?.items;
    if (Array.isArray(items)) {
      return { data: items, source: "live" };
    }
  }
  return { data: MOCK_APPROVAL_QUEUE, source: "fallback", error };
}

// ── 웹 작업 목록 ─────────────────────────────────────────────────────────────

export async function fetchWebTasks(): Promise<OpsResult<WebTaskAction[]>> {
  const { data, source, error } = await safeGet("/ops/web-tasks", null);
  if (source === "live" || source === "static") {
    const tasks = (data as { tasks?: WebTaskAction[] })?.tasks;
    if (Array.isArray(tasks)) {
      return { data: tasks, source: "live" };
    }
  }
  return { data: MOCK_WEB_TASKS, source: "fallback", error };
}

// ── 감사 이벤트 ──────────────────────────────────────────────────────────────

export async function fetchAuditEvents(limit = 20): Promise<OpsResult<AuditEventRow[]>> {
  const { data, source, error } = await safeGet(`/ops/audit-events?limit=${limit}`, null);
  if (source === "live" || source === "static") {
    const events = (data as { events?: AuditEventRow[] })?.events;
    if (Array.isArray(events)) {
      return { data: events, source: "live" };
    }
  }
  // /logs fallback
  const logsResult = await safeGet(`/logs?limit=${limit}`, null);
  if (logsResult.source === "live") {
    const logsData = logsResult.data as { events?: AuditEventRow[] } | AuditEventRow[];
    const events = Array.isArray(logsData)
      ? logsData
      : (logsData as { events?: AuditEventRow[] }).events;
    if (Array.isArray(events)) {
      return { data: events, source: "live" };
    }
  }
  return { data: MOCK_AUDIT_EVENTS, source: "fallback", error };
}

// ── 로컬 에이전트 상태 ───────────────────────────────────────────────────────

export async function fetchAgentStatuses(): Promise<OpsResult<AgentStatus[]>> {
  const { data, source, error } = await safeGet("/ops/agents", null);
  if (source === "live" || source === "static") {
    const agents = (data as { agents?: AgentStatus[] })?.agents;
    if (Array.isArray(agents)) {
      return { data: agents, source: "live" };
    }
  }
  return { data: MOCK_AGENT_STATUSES, source: "fallback", error };
}

// ── 대시보드 메트릭 ──────────────────────────────────────────────────────────

export async function fetchDashboardMetrics(): Promise<OpsResult<DashboardMetric[]>> {
  const { data, source, error } = await safeGet("/ops/summary", null);
  if (source === "live" || source === "static") {
    const metrics = (data as { metrics?: DashboardMetric[] })?.metrics;
    if (Array.isArray(metrics)) {
      return { data: metrics, source: "live" };
    }
  }
  return { data: MOCK_METRICS, source: "fallback", error };
}

// ── 연동 현황 ────────────────────────────────────────────────────────────────

export async function fetchIntegrations(): Promise<OpsResult<IntegrationStatus[]>> {
  const { data, source, error } = await safeGet("/ops/integrations", null);
  if (source === "live" || source === "static") {
    const integrations = (data as { integrations?: IntegrationStatus[] })?.integrations;
    if (Array.isArray(integrations)) {
      return { data: integrations, source: "live" };
    }
  }
  return { data: MOCK_INTEGRATIONS, source: "fallback", error };
}

// ── 레거시 호환 (기존 import 유지) ───────────────────────────────────────────
// 이전 코드가 MOCK_AUDIT_EVENTS 를 직접 반환하던 인터페이스 유지
export async function fetchApprovalQueueLegacy(): Promise<ApprovalItem[]> {
  const result = await fetchApprovalQueue();
  return result.data;
}

export async function fetchAuditEventsLegacy(limit = 20): Promise<AuditEventRow[]> {
  const result = await fetchAuditEvents(limit);
  return result.data;
}

export async function fetchAgentStatusesLegacy(): Promise<AgentStatus[]> {
  const result = await fetchAgentStatuses();
  return result.data;
}
