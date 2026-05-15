import type { WorkClassification, GateDecision, RiskLevel, AgentStatusValue } from "./types";

export const CLASSIFICATION_LABELS: Record<WorkClassification, string> = {
  IN_SCOPE: "범위 내",
  SERVER_READONLY_ALLOWED: "조회 가능",
  WEB_TASK_REGISTRY: "등록됨",
  OFFICIAL_API_OR_OAUTH_REQUIRED: "OAuth 설정 필요",
  LOCAL_AGENT_REQUIRED: "로컬 에이전트 필요",
  USER_DIRECT_REQUIRED: "사용자 직접 조작 필요",
  EXTERNAL_APP_HOLD: "별도 앱 연동 대기",
  FUTURE_INTEGRATION: "향후 연동",
  QUARANTINE_OR_HOLD: "차단됨",
};

export const CLASSIFICATION_BADGE: Record<WorkClassification, string> = {
  IN_SCOPE: "bg-green-100 text-green-800",
  SERVER_READONLY_ALLOWED: "bg-green-100 text-green-800",
  WEB_TASK_REGISTRY: "bg-blue-100 text-blue-800",
  OFFICIAL_API_OR_OAUTH_REQUIRED: "bg-yellow-100 text-yellow-800",
  LOCAL_AGENT_REQUIRED: "bg-orange-100 text-orange-800",
  USER_DIRECT_REQUIRED: "bg-purple-100 text-purple-800",
  EXTERNAL_APP_HOLD: "bg-gray-100 text-gray-600",
  FUTURE_INTEGRATION: "bg-gray-100 text-gray-500",
  QUARANTINE_OR_HOLD: "bg-red-100 text-red-700",
};

export const GATE_BADGE: Record<GateDecision, string> = {
  PASS: "bg-green-100 text-green-800",
  WARN: "bg-yellow-100 text-yellow-800",
  FAIL: "bg-red-100 text-red-800",
  HOLD: "bg-gray-100 text-gray-600",
};

export const RISK_COLOR: Record<RiskLevel, string> = {
  low: "text-green-700",
  medium: "text-yellow-700",
  high: "text-red-700",
};

export const AGENT_STATUS_BADGE: Record<AgentStatusValue, string> = {
  online: "bg-green-100 text-green-800",
  idle: "bg-blue-100 text-blue-800",
  busy: "bg-yellow-100 text-yellow-800",
  offline: "bg-gray-100 text-gray-600",
  error: "bg-red-100 text-red-800",
};

export function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  } catch {
    return iso;
  }
}
