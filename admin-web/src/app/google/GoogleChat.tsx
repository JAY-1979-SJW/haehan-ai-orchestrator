"use client";
/** 구글 허브 — 우측 AI 채팅/안내 패널 */
import { type RefObject } from "react";
import { type ChatMsg } from "./googleCatalog";

export function GoogleChat({ msgs, chatInput, setChatInput, chatRunning, onSend, endRef }: {
  msgs: ChatMsg[];
  chatInput: string;
  setChatInput: (v: string) => void;
  chatRunning: boolean;
  onSend: () => void;
  endRef: RefObject<HTMLDivElement>;
}) {
  return (
    <div className="w-full lg:w-[300px] shrink-0 flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden"
      style={{ height: "480px", position: "sticky", top: 0 }}>
      {/* 헤더 */}
      <div className="px-4 pt-4 pb-3 border-b border-[#F3F4F6] shrink-0">
        <p className="text-sm font-bold text-[#111827]">서비스 안내</p>
        <p className="text-[11px] text-[#9CA3AF] mt-0.5">카드를 클릭하면 상세 설명이 표시됩니다</p>
      </div>

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : m.role === "system" ? "justify-center" : "justify-start"}`}>
            {m.role === "system" ? (
              <span className="text-[11px] text-[#9CA3AF] italic text-center"
                dangerouslySetInnerHTML={{ __html: m.html }} />
            ) : (
              <div
                className={`max-w-full rounded-xl text-xs leading-relaxed ${
                  m.role === "user"
                    ? "px-3 py-2 bg-[#F97316] text-white rounded-br-sm"
                    : "px-3 py-3 bg-[#F9FAFB] border border-[#F3F4F6] text-[#111827] rounded-bl-sm w-full"
                }`}
                dangerouslySetInnerHTML={{ __html: m.html }}
              />
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* 입력창 */}
      <div className="px-3 pb-3 pt-2 border-t border-[#F3F4F6] shrink-0 flex gap-2">
        <input
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSend()}
          placeholder="명령어 입력..."
          className="flex-1 px-3 py-1.5 text-xs border border-[#E5E7EB] rounded-xl outline-none focus:border-[#F97316] text-[#111827] placeholder:text-[#9CA3AF]"
        />
        <button
          onClick={onSend}
          disabled={chatRunning}
          className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors shrink-0 ${
            chatRunning ? "bg-[#E5E7EB] text-[#9CA3AF]" : "bg-[#F97316] text-white hover:bg-[#EA580C]"
          }`}>
          {chatRunning ? "···" : "⚡"}
        </button>
      </div>
    </div>
  );
}
