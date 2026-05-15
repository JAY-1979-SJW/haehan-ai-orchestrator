import type { WebTaskAction } from "../lib/types";
import { CLASSIFICATION_BADGE, CLASSIFICATION_LABELS, RISK_COLOR } from "../lib/statusFormat";

const STATUS_BADGE: Record<WebTaskAction["status"], string> = {
  ready: "bg-green-100 text-green-800",
  hold: "bg-gray-100 text-gray-500",
  oauth_required: "bg-yellow-100 text-yellow-800",
  agent_required: "bg-orange-100 text-orange-800",
  blocked: "bg-red-100 text-red-800",
};

const STATUS_LABEL: Record<WebTaskAction["status"], string> = {
  ready: "실행 가능",
  hold: "HOLD",
  oauth_required: "OAuth 필요",
  agent_required: "에이전트 필요",
  blocked: "차단됨",
};

export function WebTaskPanel({ tasks }: { tasks: WebTaskAction[] }) {
  return (
    <section data-testid="web-task-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">웹 업무 등록 목록</h2>
      <div className="space-y-2">
        {tasks.map((t) => (
          <div
            key={t.taskKey}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-start justify-between">
              <div>
                <span className="font-mono text-[10px] text-gray-400 mr-2">{t.taskKey}</span>
                <span className="text-sm font-medium text-gray-800">{t.description}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium ${RISK_COLOR[t.riskLevel]}`}>
                  {t.riskLevel}
                </span>
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[t.status]}`}>
                  {STATUS_LABEL[t.status]}
                </span>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
              <span className={`rounded px-2 py-0.5 font-medium ${CLASSIFICATION_BADGE[t.classification]}`}>
                {CLASSIFICATION_LABELS[t.classification]}
              </span>
              <span>실행위치: <span className="font-mono">{t.executionLocation}</span></span>
              {t.requiresApproval && <span className="text-red-600">승인 필요</span>}
              {t.dryRunSupported && <span className="text-blue-600">dry-run 지원</span>}
            </div>
            <div className="mt-3 flex gap-2">
              <button
                disabled
                className="rounded bg-blue-100 px-3 py-1 text-xs text-blue-700 opacity-50 cursor-not-allowed"
                title="다음 공정에서 API 연결 예정"
              >
                dry-run (준비 중)
              </button>
              <button
                disabled
                className="rounded bg-green-100 px-3 py-1 text-xs text-green-700 opacity-50 cursor-not-allowed"
                title="다음 공정에서 API 연결 예정"
              >
                실행 요청 (준비 중)
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
