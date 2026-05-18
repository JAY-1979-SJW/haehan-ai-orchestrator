/** BackendStatusCard — 백엔드 Phase1 상태 카드 */
import type { BackendStatus } from "@/types/assistant";

const HEALTH_COLOR: Record<string, string> = {
  OK:      "text-[#059669]",
  WARN:    "text-[#D97706]",
  BLOCKED: "text-[#B91C1C]",
  UNKNOWN: "text-[#6B7280]",
};

export function BackendStatusCard({ status }: { status: BackendStatus }) {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[#111827]">백엔드 상태</span>
        <span className={`text-xs font-bold ${HEALTH_COLOR[status.health] ?? HEALTH_COLOR.UNKNOWN}`}>
          {status.health}
        </span>
      </div>
      <div className="text-xs text-[#6B7280] space-y-1">
        <div>HEAD: <span className="font-mono">{status.head}</span></div>
        <div>컨테이너: {status.container_status}</div>
        <div>DRY_RUN 게이트: {status.dry_run_gate_enabled
          ? <span className="text-[#059669] font-semibold">활성</span>
          : <span className="text-[#B91C1C] font-semibold">비활성</span>}
        </div>
        <div className="truncate">Phase1: {status.phase1_closeout}</div>
      </div>
    </div>
  );
}
