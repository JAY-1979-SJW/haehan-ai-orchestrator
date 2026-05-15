import type { AuditEventRow } from "../lib/types";
import { formatTimestamp } from "../lib/statusFormat";

const STATUS_BADGE: Record<AuditEventRow["status"], string> = {
  ok: "bg-green-100 text-green-800",
  warn: "bg-yellow-100 text-yellow-800",
  error: "bg-red-100 text-red-800",
  blocked: "bg-gray-200 text-gray-600",
};

export function AuditEventTable({ events }: { events: AuditEventRow[] }) {
  return (
    <section data-testid="audit-event-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">감사 이벤트 로그</h2>
      <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
        <table className="min-w-full bg-white text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2 text-left">시각</th>
              <th className="px-4 py-2 text-left">이벤트 유형</th>
              <th className="px-4 py-2 text-left">task ID</th>
              <th className="px-4 py-2 text-left">상태</th>
              <th className="px-4 py-2 text-left">요약</th>
              <th className="px-4 py-2 text-left">실행자</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.eventId} className="border-t hover:bg-gray-50">
                <td className="px-4 py-2 text-xs text-gray-500 whitespace-nowrap">
                  {formatTimestamp(e.timestamp)}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-gray-700">{e.eventType}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-400">{e.taskId}</td>
                <td className="px-4 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${STATUS_BADGE[e.status]}`}>
                    {e.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-gray-600 max-w-xs truncate">{e.summary}</td>
                <td className="px-4 py-2 text-xs text-gray-500">{e.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
