import { headers, cookies } from "next/headers";
import type { ExternalWebTaskSummary, SafetyPolicyNotice } from "./lib/types";
import {
  fetchAgentStatuses,
  fetchApprovalQueue,
  fetchAuditEvents,
  fetchDashboardMetrics,
  fetchIntegrations,
  fetchWebTasks,
} from "./lib/opsApiClient";
import { OpsDashboard } from "./components/OpsDashboard";
import { WorkTradeBoard } from "./components/WorkTradeBoard";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { WebTaskPanel } from "./components/WebTaskPanel";
import { ExternalWebTaskSummaryPanel } from "./components/ExternalWebTaskSummary";
import { AgentStatusPanel } from "./components/AgentStatusPanel";
import { GmailInboxPanel } from "./components/GmailInboxPanel";
import { MailAssistantPanel } from "./components/MailAssistantPanel";
import { GoogleToolsPanel } from "./components/GoogleToolsPanel";
import { AuditEventTable } from "./components/AuditEventTable";
import { IntegrationStatusPanel } from "./components/IntegrationStatusPanel";
import { SafetyPolicyBanner } from "./components/SafetyPolicyBanner";
import { ApiStatusBanner } from "./components/ApiStatusBanner";
import { QuotePanel } from "./components/QuotePanel";
import { PageShell } from "@/components/ui/PageShell";
import SessionStatusPanel from "@/components/SessionStatusPanel";

const SAFETY_POLICIES: SafetyPolicyNotice[] = [
  {
    id: "auth-required",
    title: "인증 필요",
    description: "운영 데이터는 인증된 응답에서만 표시됩니다.",
    level: "block",
  },
  {
    id: "no-mock-fallback",
    title: "샘플 데이터 대체 비활성",
    description: "백엔드 오류 시 샘플로 가리지 않고 그대로 표시합니다.",
    level: "warn",
  },
];

function buildExternalSummaries(tasks: Awaited<ReturnType<typeof fetchWebTasks>>["data"]): ExternalWebTaskSummary[] {
  const providers = Array.from(new Set(tasks.map((task) => task.provider)));
  return providers.map((provider) => {
    const providerTasks = tasks.filter((task) => task.provider === provider);
    return {
      provider,
      totalCount: providerTasks.length,
      readyCount: providerTasks.filter((task) => task.status === "ready").length,
      holdCount: providerTasks.filter((task) => task.status === "hold").length,
      oauthRequiredCount: providerTasks.filter((task) => task.status === "oauth_required").length,
      agentRequiredCount: providerTasks.filter((task) => task.status === "agent_required").length,
    };
  });
}

export default async function OpsPage() {
  const authHeader = headers().get("authorization");
  const cookieToken = cookies().get("haehan_ai_token")?.value;
  const authorization = authHeader ?? (cookieToken ? `Bearer ${decodeURIComponent(cookieToken)}` : null);
  const [
    metrics,
    approvalQueue,
    webTasks,
    auditEvents,
    agentStatuses,
    integrations,
  ] = await Promise.all([
    fetchDashboardMetrics(authorization),
    fetchApprovalQueue(authorization),
    fetchWebTasks(authorization),
    fetchAuditEvents(20, authorization),
    fetchAgentStatuses(authorization),
    fetchIntegrations(authorization),
  ]);

  const externalSummaries = buildExternalSummaries(webTasks.data);
  const failures = [
    metrics,
    approvalQueue,
    webTasks,
    auditEvents,
    agentStatuses,
    integrations,
  ].filter((result) => result.source !== "live");

  return (
    <PageShell title="운영센터" description="서버 상태 · 승인 · 감사 로그" chatDomain="ops">
      <div className="space-y-8">
        <ApiStatusBanner />

        {failures.length > 0 && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
            {failures.length}개 항목을 불러오지 못했습니다.
          </div>
        )}

        <SafetyPolicyBanner policies={SAFETY_POLICIES} />
        <QuotePanel />
        <OpsDashboard metrics={metrics.data} />
        <ApprovalQueue items={approvalQueue.data} />
        <WorkTradeBoard trades={[]} />
        <WebTaskPanel tasks={webTasks.data} />
        <ExternalWebTaskSummaryPanel summaries={externalSummaries} />
        <AgentStatusPanel agents={agentStatuses.data} />
        <GmailInboxPanel />
        <MailAssistantPanel />
        <GoogleToolsPanel />
        <IntegrationStatusPanel integrations={integrations.data} />
        <AuditEventTable events={auditEvents.data} />
        <SessionStatusPanel />
      </div>
    </PageShell>
  );
}
