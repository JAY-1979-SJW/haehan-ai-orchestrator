/**
 * 운영센터 API 클라이언트 스텁.
 * 백엔드 API 연결 전 fallback/mock 반환.
 * 실제 API 연결 시 각 함수의 try 블록에 fetch 추가.
 *
 * 금지: secret/token/password/session/cookie 노출
 * 금지: 실제 승인/거절 실행, 실제 위험 실행
 */
import type { ApprovalItem, AuditEventRow, AgentStatus } from "./types";
import {
  MOCK_APPROVAL_QUEUE,
  MOCK_AUDIT_EVENTS,
  MOCK_AGENT_STATUSES,
} from "./mockOpsData";

const API_BASE = "/api/v1";

async function safeGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: "Bearer admin-token" },
      cache: "no-store",
    });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

export async function fetchApprovalQueue(): Promise<ApprovalItem[]> {
  // TODO: GET /api/v1/approvals/pending 연결
  return safeGet("/approvals/pending", MOCK_APPROVAL_QUEUE);
}

export async function fetchAuditEvents(limit = 20): Promise<AuditEventRow[]> {
  const data = await safeGet<{ events?: AuditEventRow[] }>(
    `/logs?limit=${limit}`,
    {}
  );
  return (data as { events?: AuditEventRow[] }).events ?? MOCK_AUDIT_EVENTS;
}

export async function fetchAgentStatuses(): Promise<AgentStatus[]> {
  // TODO: GET /api/v1/local-agents/status 연결
  return safeGet("/local-agents/status", MOCK_AGENT_STATUSES);
}
