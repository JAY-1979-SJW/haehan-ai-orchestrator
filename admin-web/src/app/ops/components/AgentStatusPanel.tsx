import type { AgentStatus } from "../lib/types";
import { AGENT_STATUS_BADGE, formatTimestamp } from "../lib/statusFormat";

const STATUS_LABEL: Record<string, string> = {
  online: "온라인",
  offline: "오프라인",
  idle: "대기 중",
  busy: "실행 중",
  error: "오류",
};

export function AgentStatusPanel({ agents }: { agents: AgentStatus[] }) {
  return (
    <section data-testid="agent-status-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">로컬 에이전트 상태</h2>
      <div className="space-y-2">
        {agents.map((a) => (
          <div
            key={a.agentId}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium text-gray-800">{a.agentName}</span>
                <span className="ml-2 font-mono text-[10px] text-gray-400">{a.agentId}</span>
              </div>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${AGENT_STATUS_BADGE[a.status]}`}>
                {STATUS_LABEL[a.status] ?? a.status}
              </span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-1 text-xs text-gray-500">
              <div>마지막 하트비트: {formatTimestamp(a.lastHeartbeat)}</div>
              <div>
                작업 수신:{" "}
                {a.canReceiveTasks ? (
                  <span className="text-green-700">가능</span>
                ) : (
                  <span className="text-red-600">불가</span>
                )}
              </div>
              <div>
                사용자 직접 필요:{" "}
                {a.userDirectRequired ? (
                  <span className="text-yellow-700">예</span>
                ) : (
                  <span className="text-gray-500">아니요</span>
                )}
              </div>
              <div>
                서버 실행 가능:{" "}
                {a.serverExecutable ? (
                  <span className="text-green-700">예</span>
                ) : (
                  <span className="text-gray-500">아니요</span>
                )}
              </div>
              {a.blockingPolicy && (
                <div className="col-span-2 text-orange-700">정책: {a.blockingPolicy}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
