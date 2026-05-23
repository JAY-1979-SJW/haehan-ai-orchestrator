import { getBackendApiBase } from "@/lib/backend-auth";
import type {
  ApprovalItem,
  AuditEventRow,
  AgentStatus,
  WebTaskAction,
  DashboardMetric,
  IntegrationStatus,
} from "./types";

const TIMEOUT_MS = 5000;

type FetchSource = "live" | "error" | "unauthorized";

export interface OpsResult<T> {
  data: T;
  source: FetchSource;
  error?: string;
}

async function getJson(
  path: string,
  authorization?: string | null,
): Promise<{ data?: unknown; status: number; error?: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (authorization) headers.Authorization = authorization;
    const res = await fetch(`${getBackendApiBase()}${path}`, {
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) return { status: res.status, error: `HTTP ${res.status}` };
    return { status: res.status, data: await res.json() };
  } catch (err) {
    return {
      status: 0,
      error: err instanceof Error ? err.message : String(err),
    };
  } finally {
    clearTimeout(timer);
  }
}

function emptyResult<T>(data: T, status: number, error?: string): OpsResult<T> {
  return {
    data,
    source: status === 401 || status === 403 ? "unauthorized" : "error",
    error: error || "invalid_response",
  };
}

export async function fetchApprovalQueue(auth?: string | null): Promise<OpsResult<ApprovalItem[]>> {
  const result = await getJson("/ops/approvals", auth);
  const items = (result.data as { items?: ApprovalItem[] } | undefined)?.items;
  if (Array.isArray(items)) return { data: items, source: "live" };
  return emptyResult([], result.status, result.error);
}

export async function fetchWebTasks(auth?: string | null): Promise<OpsResult<WebTaskAction[]>> {
  const result = await getJson("/ops/web-tasks", auth);
  const tasks = (result.data as { tasks?: WebTaskAction[] } | undefined)?.tasks;
  if (Array.isArray(tasks)) return { data: tasks, source: "live" };
  return emptyResult([], result.status, result.error);
}

export async function fetchAuditEvents(limit = 20, auth?: string | null): Promise<OpsResult<AuditEventRow[]>> {
  const result = await getJson(`/ops/audit-events?limit=${limit}`, auth);
  const events = (result.data as { events?: AuditEventRow[] } | undefined)?.events;
  if (Array.isArray(events)) return { data: events, source: "live" };
  return emptyResult([], result.status, result.error);
}

export async function fetchAgentStatuses(auth?: string | null): Promise<OpsResult<AgentStatus[]>> {
  const result = await getJson("/ops/agents", auth);
  const agents = (result.data as { agents?: AgentStatus[] } | undefined)?.agents;
  if (Array.isArray(agents)) return { data: agents, source: "live" };
  return emptyResult([], result.status, result.error);
}

export async function fetchDashboardMetrics(auth?: string | null): Promise<OpsResult<DashboardMetric[]>> {
  const result = await getJson("/ops/summary", auth);
  const metrics = (result.data as { metrics?: DashboardMetric[] } | undefined)?.metrics;
  if (Array.isArray(metrics)) return { data: metrics, source: "live" };
  return emptyResult([], result.status, result.error);
}

export async function fetchIntegrations(auth?: string | null): Promise<OpsResult<IntegrationStatus[]>> {
  const result = await getJson("/ops/integrations", auth);
  const integrations = (result.data as { integrations?: IntegrationStatus[] } | undefined)?.integrations;
  if (Array.isArray(integrations)) return { data: integrations, source: "live" };
  return emptyResult([], result.status, result.error);
}

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
