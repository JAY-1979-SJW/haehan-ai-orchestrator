"use client";
import { registerDomainChat } from "@/components/chat/domainChatRegistry";
/**
 * SmartStoreChat — 2026-09-24: 앱 런타임 채팅(구 /api/smartstore/chat, Anthropic/OpenAI
 * 백엔드) 제거. AI 작업은 Claude Code(MCP: haehan-orchestrator)로 수행한다.
 * 조회·쓰기 기능 자체는 ai_orchestrator/connectors/smartstore/* REST 엔드포인트로
 * 그대로 남아 있고, Claude Code가 MCP call_api로 호출한다.
 */
export default function SmartStoreChat() {
  return (
    <div className="flex flex-col h-full min-h-[400px] border border-[#E5E7EB] rounded-2xl bg-white overflow-hidden">
      <div className="shrink-0 flex items-center gap-2 px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
        <span className="w-7 h-7 rounded-lg bg-[#F97316] flex items-center justify-center text-white text-xs font-bold shrink-0">AI</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-[#111827]">스마트스토어 AI 에이전트</p>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <p className="text-xs text-[#6B7280] text-center leading-relaxed max-w-xs">
          앱 내 AI 채팅은 제거되었습니다 — AI 작업은 Claude Code(MCP: haehan-orchestrator)로 합니다.
        </p>
      </div>
    </div>
  );
}

registerDomainChat("smartstore", SmartStoreChat); // 공용 AI 패널(AiDock)이 이 화면을 직접 import 하지 않도록 등록한다
