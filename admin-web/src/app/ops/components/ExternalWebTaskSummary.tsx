import type { ExternalWebTaskSummary } from "../lib/types";

export function ExternalWebTaskSummaryPanel({ summaries }: { summaries: ExternalWebTaskSummary[] }) {
  return (
    <section data-testid="external-web-task-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">외부 웹 업무 현황</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {summaries.map((s) => (
          <div
            key={s.provider}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold text-gray-800 capitalize">{s.provider}</span>
              <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                전체 {s.totalCount}건
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">실행 가능</span>
                <span className="font-medium text-green-700">{s.readyCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">HOLD</span>
                <span className="font-medium text-gray-500">{s.holdCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">OAuth 필요</span>
                <span className="font-medium text-yellow-700">{s.oauthRequiredCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">에이전트 필요</span>
                <span className="font-medium text-orange-700">{s.agentRequiredCount}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
