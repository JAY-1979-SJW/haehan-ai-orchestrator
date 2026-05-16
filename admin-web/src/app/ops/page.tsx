import {
  MOCK_METRICS,
  MOCK_WORK_TRADES,
  MOCK_APPROVAL_QUEUE,
  MOCK_WEB_TASKS,
  MOCK_AGENT_STATUSES,
  MOCK_AUDIT_EVENTS,
  MOCK_INTEGRATIONS,
  SAFETY_POLICIES,
} from "./lib/mockOpsData";
import type { ExternalWebTaskSummary } from "./lib/types";
import { OpsDashboard } from "./components/OpsDashboard";
import { WorkTradeBoard } from "./components/WorkTradeBoard";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { WebTaskPanel } from "./components/WebTaskPanel";
import { ExternalWebTaskSummaryPanel } from "./components/ExternalWebTaskSummary";
import { AgentStatusPanel } from "./components/AgentStatusPanel";
import { AuditEventTable } from "./components/AuditEventTable";
import { IntegrationStatusPanel } from "./components/IntegrationStatusPanel";
import { SafetyPolicyBanner } from "./components/SafetyPolicyBanner";
import { ApiStatusBanner } from "./components/ApiStatusBanner";

function buildExternalSummaries(): ExternalWebTaskSummary[] {
  const providers = ["naver", "google"];
  return providers.map((provider) => {
    const tasks = MOCK_WEB_TASKS.filter((t) => t.provider === provider);
    return {
      provider,
      totalCount: tasks.length,
      readyCount: tasks.filter((t) => t.status === "ready").length,
      holdCount: tasks.filter((t) => t.status === "hold").length,
      oauthRequiredCount: tasks.filter((t) => t.status === "oauth_required").length,
      agentRequiredCount: tasks.filter((t) => t.status === "agent_required").length,
    };
  });
}

export default function OpsPage() {
  const externalSummaries = buildExternalSummaries();

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-6 sm:px-6">
      <div className="mx-auto max-w-7xl space-y-8">
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">운영센터</h1>
            <p className="mt-0.5 text-xs text-gray-400">
              비서앱 · 작업 승인 · 에이전트 · 감사 로그 통합 운영
            </p>
          </div>
          <a
            href="/"
            className="rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-200"
          >
            ← 홈으로
          </a>
        </div>

        {/* API 연결 상태 배너 */}
        <ApiStatusBanner />

        {/* 안전 정책 */}
        <SafetyPolicyBanner policies={SAFETY_POLICIES} />

        {/* 운영 대시보드 */}
        <OpsDashboard metrics={MOCK_METRICS} />

        {/* 승인 대기 */}
        <ApprovalQueue items={MOCK_APPROVAL_QUEUE} />

        {/* 공종 관리 */}
        <WorkTradeBoard trades={MOCK_WORK_TRADES} />

        {/* 웹 업무 목록 */}
        <WebTaskPanel tasks={MOCK_WEB_TASKS} />

        {/* 외부 웹 업무 현황 */}
        <ExternalWebTaskSummaryPanel summaries={externalSummaries} />

        {/* 로컬 에이전트 상태 */}
        <AgentStatusPanel agents={MOCK_AGENT_STATUSES} />

        {/* 연동 현황 */}
        <IntegrationStatusPanel integrations={MOCK_INTEGRATIONS} />

        {/* 감사 이벤트 */}
        <AuditEventTable events={MOCK_AUDIT_EVENTS} />
      </div>
    </main>
  );
}
