"use client";

interface Props {
  domain?: string;
  title?: string;
  className?: string;
}

// 2026-09-24: 앱 런타임 채팅(GPT/OpenAI 백엔드) 제거. AI 작업은 Claude Code(MCP:
// haehan-orchestrator)로 수행한다. 이 컴포넌트는 이전 채팅 UI가 있던 자리에
// 정적 안내만 표시한다 — presetChips/스트리밍/confirm 등 관련 로직은 전부 제거.
export function UniversalChat({ title, className = "" }: Props) {
  return (
    <div className={`flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden ${className}`}>
      <div className="px-4 py-3 border-b border-[#F3F4F6] shrink-0">
        <p className="text-sm font-bold text-[#111827]">{title ?? "AI 어시스턴트"}</p>
      </div>
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <p className="text-xs text-[#6B7280] text-center leading-relaxed">
          앱 내 AI 채팅은 제거되었습니다 — AI 작업은 Claude Code(MCP: haehan-orchestrator)로 합니다.
        </p>
      </div>
    </div>
  );
}
