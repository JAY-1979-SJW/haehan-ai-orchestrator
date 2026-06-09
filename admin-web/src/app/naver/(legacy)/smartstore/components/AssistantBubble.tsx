"use client";
import type { AiBlock, ActionChip } from "./types";
import { BlockView } from "./BlockView";

export function AssistantBubble({
  blocks,
  streaming,
  actions,
  onAction,
  pendingConfirm,
  onConfirm,
  onCancelConfirm,
}: {
  blocks: AiBlock[];
  streaming: boolean;
  actions?: ActionChip[];
  onAction?: (prompt: string) => void;
  pendingConfirm: { tool: string; inputs: Record<string, unknown>; message: string } | null;
  onConfirm: () => void;
  onCancelConfirm: () => void;
}) {
  const isEmpty = blocks.length === 0;

  return (
    <div className="flex justify-start gap-2">
      <div className="w-7 h-7 rounded-lg bg-[#F97316] flex items-center justify-center text-white text-xs font-bold shrink-0 mt-1">
        AI
      </div>
      <div className="flex flex-col gap-1 max-w-[80%]">
        <div className="min-w-[120px] bg-[#F9FAFB] border border-[#E5E7EB] rounded-2xl rounded-tl-md px-4 py-3 space-y-2 shadow-sm">
          {isEmpty && streaming && (
            <span className="flex gap-1 items-center h-5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce [animation-delay:300ms]" />
            </span>
          )}

          {blocks.map((block, i) => (
            <BlockView
              key={i}
              block={block}
              pendingConfirm={pendingConfirm}
              onConfirm={onConfirm}
              onCancelConfirm={onCancelConfirm}
            />
          ))}

          {streaming && blocks.length > 0 && (
            <span className="inline-block w-1.5 h-4 bg-[#F97316] animate-pulse rounded-sm" />
          )}
        </div>

        {/* B. 후속 액션 버튼 */}
        {!streaming && actions && actions.length > 0 && onAction && (
          <div className="flex flex-wrap gap-1">
            {actions.map((a) => (
              <button key={a.label} onClick={() => onAction(a.prompt)}
                className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white text-[#6B7280] border border-[#E5E7EB] hover:bg-[#F3F4F6] hover:text-[#111827] transition-colors">
                {a.label} →
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
