/** ApiConnectionStateBadge — API 연결 상태 배지 */
import type { ApiConnectionMeta } from "@/types/assistant";

type LoadState = "idle" | "loading" | "success" | "empty" | "error" | "mock_fallback";

interface Props {
  state: LoadState;
  meta?: Partial<ApiConnectionMeta>;
  label?: string;
}

const STATE_STYLE: Record<LoadState, string> = {
  idle:          "bg-[#F3F4F6] text-[#6B7280]",
  loading:       "bg-[#FEF3C7] text-[#92400E] animate-pulse",
  success:       "bg-[#DCFCE7] text-[#166534]",
  empty:         "bg-[#F3F4F6] text-[#9CA3AF]",
  error:         "bg-[#FEE2E2] text-[#B91C1C]",
  mock_fallback: "bg-[#FEF9C3] text-[#713F12]",
};

const STATE_LABEL: Record<LoadState, string> = {
  idle:          "IDLE",
  loading:       "연결 중…",
  success:       "API 연결",
  empty:         "EMPTY",
  error:         "ERROR",
  mock_fallback: "MOCK_FALLBACK",
};

export function ApiConnectionStateBadge({ state, meta, label }: Props) {
  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-[10px] ${STATE_STYLE[state]}`}>
      {label ? `${label}: ` : ""}{STATE_LABEL[state]}
      {meta?.source && state === "success" && (
        <span className="opacity-60">({meta.source})</span>
      )}
      {meta?.last_checked && state === "success" && (
        <span className="opacity-50 text-[9px]">{meta.last_checked.slice(11, 19)}</span>
      )}
    </span>
  );
}
