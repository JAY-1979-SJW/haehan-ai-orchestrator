"use client";
/**
 * AgentCommandBar — 자연어 명령창(구). 백엔드 /smartstore/chat 가 삭제되어
 * (ai_orchestrator/connectors/smartstore/chat.py docstring 참고 — AI 작업은
 * 이제 Claude Code가 MCP로 앱 API를 직접 호출해 수행) 끊긴 채 방치돼 있었다
 * (R1 API 계약 감사, 2026-10-07). 명령창 자리를 AI 작업 콘솔 안내로 교체.
 */
import Link from "next/link";

export default function AgentCommandBar() {
  return (
    <div className="border border-[#E5E7EB] rounded-2xl bg-white overflow-hidden mb-4">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
        <span className="text-sm font-bold text-[#111827]">AI 명령</span>
      </div>
      <div className="p-4 text-sm text-[#374151] space-y-2">
        <p>이 화면의 자연어 명령창은 더 이상 지원되지 않습니다.</p>
        <p>
          AI 작업은{" "}
          <Link href="/" className="text-[#F97316] font-semibold hover:underline">
            AI 작업 콘솔
          </Link>
          에서 요청하세요.
        </p>
      </div>
    </div>
  );
}
