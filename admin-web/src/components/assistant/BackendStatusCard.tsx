/** BackendStatusCard — 백엔드 Phase1 상태 카드 (APP_UI_READONLY_BACKEND_STATUS_CARDS_01 보강) */
import type { BackendStatus } from "@/types/assistant";

const HEALTH_COLOR: Record<string, string> = {
  OK:       "text-[#059669]",
  WARN:     "text-[#D97706]",
  BLOCKED:  "text-[#B91C1C]",
  UNKNOWN:  "text-[#6B7280]",
  DEGRADED: "text-[#D97706]",
  MOCK:     "text-[#9CA3AF]",
};

const SOURCE_LABEL: Record<string, string> = {
  api:          "API",
  mock:         "MOCK",
  static:       "STATIC",
  mock_fallback:"MOCK_FALLBACK",
};

export function BackendStatusCard({ status }: { status: BackendStatus }) {
  const meta = status.api_meta;
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[#111827]">백엔드 상태</span>
        <div className="flex items-center gap-1.5">
          {meta && (
            <span className="text-[9px] font-mono bg-[#F3F4F6] text-[#6B7280] px-1.5 py-0.5 rounded">
              {SOURCE_LABEL[meta.source] ?? meta.source}
            </span>
          )}
          <span className={`text-xs font-bold ${HEALTH_COLOR[status.health] ?? HEALTH_COLOR.UNKNOWN}`}>
            {status.health}
          </span>
        </div>
      </div>
      <div className="text-xs text-[#6B7280] space-y-1">
        <div>HEAD: <span className="font-mono">{status.head}</span></div>
        <div>컨테이너: {status.container_status}</div>
        <div>
          DRY_RUN 게이트:{" "}
          {status.dry_run_gate_enabled
            ? <span className="text-[#059669] font-semibold">활성 (POST_TASKS_DRY_RUN_ENABLED=True)</span>
            : <span className="text-[#B91C1C] font-semibold">비활성</span>}
        </div>
        <div className="truncate">Phase1: {status.phase1_closeout}</div>
        {meta?.last_checked && (
          <div className="text-[#9CA3AF]">
            최종 확인: <span className="font-mono">{meta.last_checked}</span>
          </div>
        )}
        {meta?.error_kind && (
          <div className="text-[#F59E0B]">
            오류 유형: <span className="font-mono">{meta.error_kind}</span>
            {" "}(상세 정보 표시 금지)
          </div>
        )}
      </div>
      <div className="pt-1 border-t border-[#F3F4F6] flex items-center gap-2">
        <span className="text-[10px] font-mono bg-[#EFF6FF] text-[#1D4ED8] px-1.5 py-0.5 rounded">
          mutation_allowed=false
        </span>
        <span className="text-[10px] font-mono bg-[#F0FDF4] text-[#166534] px-1.5 py-0.5 rounded">
          is_read_only=true
        </span>
      </div>
    </div>
  );
}
