import type { WorkTrade } from "../lib/types";
import {
  CLASSIFICATION_LABELS,
  CLASSIFICATION_BADGE,
  GATE_BADGE,
  RISK_COLOR,
} from "../lib/statusFormat";

export function WorkTradeBoard({ trades }: { trades: WorkTrade[] }) {
  return (
    <section data-testid="work-trade-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">공종 관리</h2>
      <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
        <table className="min-w-full bg-white text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2 text-left">공종명</th>
              <th className="px-4 py-2 text-left">설명</th>
              <th className="px-4 py-2 text-left">범위 분류</th>
              <th className="px-4 py-2 text-left">위험도</th>
              <th className="px-4 py-2 text-left">승인</th>
              <th className="px-4 py-2 text-left">상태</th>
              <th className="px-4 py-2 text-left">비고</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.tradeKey} className="border-t hover:bg-gray-50">
                <td className="px-4 py-2 font-medium text-gray-800">{t.tradeName}</td>
                <td className="px-4 py-2 text-gray-500 text-xs max-w-xs truncate">{t.description}</td>
                <td className="px-4 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${CLASSIFICATION_BADGE[t.classification]}`}>
                    {CLASSIFICATION_LABELS[t.classification]}
                  </span>
                </td>
                <td className={`px-4 py-2 text-xs font-medium ${RISK_COLOR[t.riskLevel]}`}>
                  {t.riskLevel}
                </td>
                <td className="px-4 py-2 text-xs">
                  {t.requiresApproval ? (
                    <span className="text-red-600">필요</span>
                  ) : (
                    <span className="text-green-600">불필요</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${GATE_BADGE[t.status]}`}>
                    {t.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-gray-400">{t.notes ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
