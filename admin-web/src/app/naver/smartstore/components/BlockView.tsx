import type { AiBlock } from "./types";
import { TOOL_LABEL } from "./constants";

export function BlockView({
  block,
  pendingConfirm,
  onConfirm,
  onCancelConfirm,
}: {
  block: AiBlock;
  pendingConfirm: { tool: string; inputs: Record<string, unknown>; message: string } | null;
  onConfirm: () => void;
  onCancelConfirm: () => void;
}) {
  if (block.type === "text") {
    return <p className="text-sm text-[#111827] leading-relaxed whitespace-pre-wrap">{block.text}</p>;
  }

  if (block.type === "step") {
    const { item } = block;
    const icon =
      item.status === "running" ? <span className="w-3 h-3 rounded-full bg-[#F97316] animate-pulse shrink-0" /> :
      item.status === "ok"      ? <span className="text-[#16A34A] font-bold text-sm shrink-0">✓</span> :
                                  <span className="text-[#DC2626] font-bold text-sm shrink-0">✗</span>;
    return (
      <div className="flex items-center gap-2 text-xs py-1 px-2 bg-white rounded-lg border border-[#E5E7EB]">
        <span className="w-5 h-5 rounded-full bg-[#F3F4F6] border border-[#E5E7EB] flex items-center justify-center text-[10px] font-bold text-[#6B7280] shrink-0">
          {item.step}
        </span>
        {icon}
        <span className={`font-medium ${item.write ? "text-[#C2410C]" : "text-[#1D4ED8]"}`}>
          {TOOL_LABEL[item.tool] ?? item.tool}
        </span>
        {item.write && (
          <span className="text-[10px] bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded font-semibold">
            쓰기
          </span>
        )}
        {item.detail && <span className="text-[#DC2626] truncate">{item.detail}</span>}
      </div>
    );
  }

  if (block.type === "confirm") {
    const active = !!pendingConfirm;
    return (
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-3 space-y-2">
        <p className="text-xs font-semibold text-[#C2410C]">작업 승인 필요</p>
        <p className="text-xs text-[#92400E]">{block.message}</p>
        <div className="bg-white border border-[#FED7AA] rounded-lg p-2 space-y-1">
          {Object.entries(block.inputs).map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs">
              <span className="font-mono text-[#92400E] w-20 shrink-0">{k}</span>
              <span className="text-[#111827]">{String(v)}</span>
            </div>
          ))}
        </div>
        {active && (
          <div className="flex gap-2 pt-1">
            <button
              onClick={onConfirm}
              className="flex-1 py-1.5 rounded-lg bg-[#F97316] text-white text-xs font-semibold hover:bg-[#EA580C] transition-colors"
            >
              승인하고 실행
            </button>
            <button
              onClick={onCancelConfirm}
              className="flex-1 py-1.5 rounded-lg border border-[#E5E7EB] text-xs text-[#6B7280] hover:bg-[#F9FAFB] transition-colors"
            >
              취소
            </button>
          </div>
        )}
      </div>
    );
  }

  if (block.type === "done") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#16A34A] font-semibold pt-1">
        <span>✓</span>
        <span>완료 — {block.steps}단계 처리됨</span>
      </div>
    );
  }

  if (block.type === "error") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#DC2626] bg-[#FEF2F2] border border-[#FECACA] rounded-lg px-3 py-2">
        <span className="font-bold shrink-0">✗</span>
        <span>{block.message}</span>
      </div>
    );
  }

  return null;
}
