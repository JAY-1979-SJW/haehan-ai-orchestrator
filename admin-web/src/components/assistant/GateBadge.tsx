/** GateBadge — 승인 게이트 상태 배지 */
import type { GateState } from "@/types/assistant";

const GATE_CONFIG: Record<GateState, { label: string; classes: string }> = {
  DISPLAY_ONLY:  { label: "표시만",        classes: "bg-[#F3F4F6] text-[#374151] border-[#D1D5DB]" },
  DISABLED:      { label: "비활성",        classes: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" },
  HIDDEN:        { label: "숨김(금지)",    classes: "bg-[#FEE2E2] text-[#991B1B] border-[#FECACA]" },
  DRY_RUN_ONLY:  { label: "드라이런만",   classes: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]" },
};

export function GateBadge({ state }: { state: GateState }) {
  const cfg = GATE_CONFIG[state] ?? GATE_CONFIG.DISPLAY_ONLY;
  return (
    <span className={`inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border ${cfg.classes}`}>
      {cfg.label}
    </span>
  );
}
