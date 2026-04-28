import type {
  CancelTaskResponse,
  LocalAgentsResponse,
  LocalAgentTasksResponse,
} from "@/types/local-agent";

export const API_BASE_PATH = "/api/v1";

export function buildApiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (normalized.startsWith("/api/v1")) return normalized;
  return `${API_BASE_PATH}${normalized}`;
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
