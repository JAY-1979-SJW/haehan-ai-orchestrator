// 운영센터 공통 타입 정의

export type WorkClassification =
  | "IN_SCOPE"
  | "SERVER_READONLY_ALLOWED"
  | "WEB_TASK_REGISTRY"
  | "OFFICIAL_API_OR_OAUTH_REQUIRED"
  | "LOCAL_AGENT_REQUIRED"
  | "USER_DIRECT_REQUIRED"
  | "EXTERNAL_APP_HOLD"
  | "FUTURE_INTEGRATION"
  | "QUARANTINE_OR_HOLD";

export type RiskLevel = "low" | "medium" | "high";
export type ExecutionLocation = "SERVER" | "LOCAL_AGENT" | "USER_DIRECT" | "OFFICIAL_API";
export type ApprovalStatus = "pending_approval" | "approved" | "rejected" | "expired";
export type AgentStatusValue = "online" | "offline" | "idle" | "busy" | "error";
export type GateDecision = "PASS" | "WARN" | "FAIL" | "HOLD";

export interface DashboardMetric {
  label: string;
  value: string | number;
  sub?: string;
  status?: GateDecision;
}

export interface WorkTrade {
  tradeKey: string;
  tradeName: string;
  description: string;
  classification: WorkClassification;
  executionLocation: ExecutionLocation;
  riskLevel: RiskLevel;
  requiresApproval: boolean;
  requiresAuth: boolean;
  status: GateDecision;
  notes?: string;
}

export interface ApprovalItem {
  taskId: string;
  taskName: string;
  provider: string;
  actionType: string;
  riskLevel: RiskLevel;
  requestedAt: string;
  expiresAt: string;
  status: ApprovalStatus;
  requestedBy: string;
}

export interface WebTaskAction {
  taskKey: string;
  provider: string;
  actionType: string;
  description: string;
  executionLocation: ExecutionLocation;
  riskLevel: RiskLevel;
  requiresApproval: boolean;
  dryRunSupported: boolean;
  classification: WorkClassification;
  status: "ready" | "hold" | "oauth_required" | "agent_required" | "blocked";
}

export interface ExternalWebTaskSummary {
  provider: string;
  totalCount: number;
  readyCount: number;
  holdCount: number;
  oauthRequiredCount: number;
  agentRequiredCount: number;
}

export interface AgentStatus {
  agentId: string;
  agentName: string;
  status: AgentStatusValue;
  lastHeartbeat: string;
  canReceiveTasks: boolean;
  userDirectRequired: boolean;
  serverExecutable: boolean;
  blockingPolicy?: string;
}

export interface AuditEventRow {
  eventId: string;
  eventType: string;
  taskId: string;
  status: "ok" | "warn" | "error" | "blocked";
  timestamp: string;
  actor: string;
  summary: string;
}

export interface IntegrationStatus {
  key: string;
  name: string;
  classification: WorkClassification;
  connected: boolean;
  authMethod: string;
  notes: string;
  action?: string;
}

export interface SafetyPolicyNotice {
  id: string;
  title: string;
  description: string;
  level: "info" | "warn" | "block";
}
