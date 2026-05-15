import type { DashboardMetric } from "../lib/types";
import { GATE_BADGE } from "../lib/statusFormat";

export function OpsDashboard({ metrics }: { metrics: DashboardMetric[] }) {
  return (
    <section data-testid="ops-dashboard-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">운영 대시보드</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {metrics.map((m) => (
          <div
            key={m.label}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="text-xs text-gray-500">{m.label}</div>
            <div className="mt-1 text-2xl font-bold text-gray-900">{m.value}</div>
            {m.sub && <div className="text-xs text-gray-400">{m.sub}</div>}
            {m.status && (
              <span
                className={`mt-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${GATE_BADGE[m.status]}`}
              >
                {m.status}
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
