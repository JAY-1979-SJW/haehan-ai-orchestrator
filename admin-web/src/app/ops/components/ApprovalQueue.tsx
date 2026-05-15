import type { ApprovalItem } from "../lib/types";
import { RISK_COLOR, formatTimestamp } from "../lib/statusFormat";

export function ApprovalQueue({ items }: { items: ApprovalItem[] }) {
  return (
    <section data-testid="approval-queue-section">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">승인 대기</h2>
        <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
          {items.length}건 대기
        </span>
      </div>
      {items.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-sm text-gray-400">
          승인 대기 항목 없음
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.taskId}
              className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-start justify-between">
                <div>
                  <span className="font-mono text-[10px] text-gray-400 mr-2">{item.taskId}</span>
                  <span className="text-sm font-medium text-gray-800">{item.taskName}</span>
                </div>
                <span className={`text-xs font-medium ${RISK_COLOR[item.riskLevel]}`}>
                  위험도: {item.riskLevel}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-500">
                <div>provider: <span className="font-mono">{item.provider}</span></div>
                <div>action: <span className="font-mono">{item.actionType}</span></div>
                <div>요청: {formatTimestamp(item.requestedAt)}</div>
                <div>만료: {formatTimestamp(item.expiresAt)}</div>
                <div>요청자: {item.requestedBy}</div>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  disabled
                  className="rounded bg-green-200 px-3 py-1 text-xs text-green-700 opacity-50 cursor-not-allowed"
                  title="다음 공정에서 API 연결 예정"
                >
                  승인 (준비 중)
                </button>
                <button
                  disabled
                  className="rounded bg-red-100 px-3 py-1 text-xs text-red-600 opacity-50 cursor-not-allowed"
                  title="다음 공정에서 API 연결 예정"
                >
                  거절 (준비 중)
                </button>
                <button
                  disabled
                  className="rounded bg-gray-100 px-3 py-1 text-xs text-gray-500 opacity-50 cursor-not-allowed"
                >
                  상세 보기
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
