import type {
  ApprovalRequest,
  ApprovalResponse,
  CancelTaskResponse,
  CaptureScreenshotResponse,
  LocalAgentTaskDetail,
  LocalAgentsResponse,
  LocalAgentTasksResponse,
  LocalAgentDiagnosticsResponse,
} from "@/types/local-agent";
import type { CurrentUser } from "@/types/auth";

const DEFAULT_API_BASE_PATH = "/orchestrator/api/v1";

export const API_BASE_PATH =
  process.env.NEXT_PUBLIC_API_BASE_PATH ?? DEFAULT_API_BASE_PATH;

export function buildApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (normalized.startsWith(API_BASE_PATH)) return normalized;
  if (normalized.startsWith("/api/v1"))
    return API_BASE_PATH + normalized.slice("/api/v1".length);
  return API_BASE_PATH + normalized;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = buildApiUrl(path);
  const res = await fetch(url, { credentials: "same-origin", ...options });

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export function getLocalAgents(): Promise<LocalAgentsResponse> {
  return apiFetch<LocalAgentsResponse>("/local-agents");
}

export function getAgentTasks(
  agentId: string,
  options?: { status?: string; limit?: number }
): Promise<LocalAgentTasksResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options?.limit ?? 50));
  if (options?.status) params.set("status", options.status);
  return apiFetch<LocalAgentTasksResponse>(
    `/local-agents/${encodeURIComponent(agentId)}/tasks?${params.toString()}`
  );
}

export function cancelTask(
  agentId: string,
  taskId: string,
  reason = ""
): Promise<CancelTaskResponse> {
  return apiFetch<CancelTaskResponse>(
    `/local-agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}/cancel`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }
  );
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/me");
}

export function getLocalAgentTask(
  agentId: string,
  taskId: string
): Promise<LocalAgentTaskDetail> {
  return apiFetch<LocalAgentTaskDetail>(
    `/local-agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}`
  );
}

export function approveLocalAgentTask(
  agentId: string,
  taskId: string,
  body: ApprovalRequest
): Promise<ApprovalResponse> {
  return apiFetch<ApprovalResponse>(
    `/local-agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
}

export function rejectLocalAgentTask(
  agentId: string,
  taskId: string,
  body: ApprovalRequest
): Promise<ApprovalResponse> {
  return apiFetch<ApprovalResponse>(
    `/local-agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
}

export function requestCaptureScreenshot(
  agentId: string,
  options?: {
    dryRun?: boolean;
    reason?: string;
    note?: string;
  }
): Promise<CaptureScreenshotResponse> {
  return apiFetch<CaptureScreenshotResponse>(
    `/local-agents/${encodeURIComponent(agentId)}/capture-screenshot`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dry_run: options?.dryRun ?? true,
        reason: options?.reason ?? "",
        note: options?.note ?? "",
      }),
    }
  );
}

export function getLocalAgentsDiagnostics(): Promise<LocalAgentDiagnosticsResponse> {
  return apiFetch<LocalAgentDiagnosticsResponse>("/local-agents/diagnostics");
}
