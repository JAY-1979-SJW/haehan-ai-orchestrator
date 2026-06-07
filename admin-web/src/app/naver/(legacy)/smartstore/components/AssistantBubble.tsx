"use client";
import type { AiBlock } from "./types";
import { BlockView } from "./BlockView";

export function AssistantBubble({
  blocks,
  streaming,
  pendingConfirm,
  onConfirm,
  onCancelConfirm,
}: {
  blocks: AiBlock[];
  streaming: boolean;
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
      <div className="max-w-[80%] min-w-[120px] bg-[#F9FAFB] border border-[#E5E7EB] rounded-2xl rounded-tl-md px-4 py-3 space-y-2 shadow-sm">
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
    </div>
  );
}
