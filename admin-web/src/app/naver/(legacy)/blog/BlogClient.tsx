"use client";
/**
 * BlogClient — 네이버 블로그 (thin 패턴)
 *
 * 2026-09-24: 앱 런타임 채팅(구 /api/chat → /api/v1/agent-ai/chat → free_agent) 제거.
 * 제목·본문·태그 생성 및 네이버 발행은 이제 Claude Code(MCP: haehan-orchestrator)가
 * 사용자 지시에 따라 직접 수행한다. 이 화면은 정적 안내만 표시한다.
 */
import { UniversalChat } from "@/components/chat/UniversalChat";

export default function BlogClient() {
  return (
    <div className="space-y-4">
      {/* 정책 안내 */}
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl px-4 py-3 flex items-start gap-3">
        <span className="text-[#F97316] text-base mt-0.5">!</span>
        <div>
          <p className="text-xs font-bold text-[#C2410C]">AI 작업은 Claude Code로 진행합니다</p>
          <p className="text-xs text-[#78350F] mt-0.5">
            앱 내 AI 채팅은 제거되었습니다 — AI 작업은 Claude Code(MCP: haehan-orchestrator)로 합니다.
            외부 발행 등 위험 동작은 매번 확인 후 진행됩니다.
          </p>
        </div>
      </div>

      {/* 안내 패널 (앱 내 채팅 제거됨) */}
      <UniversalChat
        domain="blog"
        title="네이버 블로그 AI"
        className="h-[calc(100vh-220px)] min-h-[420px]"
      />
    </div>
  );
}
