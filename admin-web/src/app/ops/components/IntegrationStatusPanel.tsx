import type { IntegrationStatus } from "../lib/types";
import { CLASSIFICATION_BADGE, CLASSIFICATION_LABELS } from "../lib/statusFormat";

export function IntegrationStatusPanel({ integrations }: { integrations: IntegrationStatus[] }) {
  return (
    <section data-testid="integration-status-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">연동 현황</h2>
      <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
        <table className="min-w-full bg-white text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2 text-left">연동 서비스</th>
              <th className="px-4 py-2 text-left">분류</th>
              <th className="px-4 py-2 text-left">연결</th>
              <th className="px-4 py-2 text-left">인증 방식</th>
              <th className="px-4 py-2 text-left">비고</th>
              <th className="px-4 py-2 text-left">액션</th>
            </tr>
          </thead>
          <tbody>
            {integrations.map((i) => (
              <tr key={i.key} className="border-t hover:bg-gray-50">
                <td className="px-4 py-2 font-medium text-gray-800">{i.name}</td>
                <td className="px-4 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${CLASSIFICATION_BADGE[i.classification]}`}>
                    {CLASSIFICATION_LABELS[i.classification]}
                  </span>
                </td>
                <td className="px-4 py-2">
                  {i.connected ? (
                    <span className="text-xs font-medium text-green-700">연결됨</span>
                  ) : (
                    <span className="text-xs font-medium text-gray-400">미연결</span>
                  )}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-gray-500">{i.authMethod}</td>
                <td className="px-4 py-2 text-xs text-gray-400 max-w-xs truncate">{i.notes}</td>
                <td className="px-4 py-2">
                  {i.action ? (
                    <button
                      disabled
                      className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-600 opacity-50 cursor-not-allowed"
                      title="다음 공정에서 API 연결 예정"
                    >
                      {i.action}
                    </button>
                  ) : (
                    <span className="text-xs text-gray-300">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
