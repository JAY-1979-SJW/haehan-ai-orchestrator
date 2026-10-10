"use client";

import { type Dispatch, type SetStateAction, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { domainChatVersion, getDomainChat, subscribeDomainChat } from "./domainChatRegistry";
import { UniversalChat } from "./UniversalChat";

/** 현재 경로 → AI 도메인 추론. 도구가 완비된 스마트스토어는 풀 에이전트로 분기. */
function domainFromPath(path: string): string {
  if (path.startsWith("/naver/smartstore")) return "smartstore";
  if (path.startsWith("/naver/blog")) return "blog";
  if (path.startsWith("/naver/keywords")) return "keywords";
  if (path.startsWith("/naver/cafe") || path.startsWith("/assistant/cafe")) return "cafe";
  if (path.startsWith("/google") || path.startsWith("/youtube")) return "google";
  if (path.startsWith("/gabia")) return "gabia";
  if (path.startsWith("/eum")) return "eum";
  if (path.startsWith("/market-research")) return "market";
  if (path.startsWith("/grant-radar")) return "grant";
  return "default";
}

const HIDE_PREFIXES = ["/login", "/about", "/signup"];

/** 우측 상시 AI 상담 패널. 보는 화면(도메인)에 맞춰 연동, 모든 앱 도구를 AI가 사용. */
export function AiDock({ open, setOpen }: { open: boolean; setOpen: Dispatch<SetStateAction<boolean>> }) {
  const pathname = usePathname() ?? "";
  // 전용 패널을 가진 화면(예: 스마트스토어)이 등록하면 다시 그린다
  useSyncExternalStore(subscribeDomainChat, domainChatVersion, domainChatVersion);
  if (HIDE_PREFIXES.some((p) => pathname.startsWith(p))) return null;

  const domain = domainFromPath(pathname);
  const DomainPanel = getDomainChat(domain);
  const panel = DomainPanel ? (
    <DomainPanel />
  ) : (
    <UniversalChat domain={domain} title="AI 어시스턴트" className="h-full rounded-none border-0" />
  );
  const header = (
    <div className="flex items-center justify-between px-3 h-[44px] border-b border-[#F3F4F6] bg-[#FFF7ED] shrink-0">
      <span className="text-xs font-bold text-[#C2410C]">🤖 AI 상담 · {domain === "smartstore" ? "스마트스토어" : domain}</span>
      <button onClick={() => setOpen(false)} title="패널 접기"
        className="text-[#9CA3AF] hover:text-[#111827] text-sm px-1">✕</button>
    </div>
  );

  return (
    <>
      {/* ── 데스크톱: 우측 상시 패널 ── */}
      {open && (
        <aside className="hidden lg:flex fixed top-0 right-0 bottom-0 w-[360px] z-40 flex-col border-l border-[#E5E7EB] bg-white shadow-[-8px_0_24px_rgba(15,23,42,0.06)]">
          <div className="h-1 bg-[#F97316] shrink-0" />
          {header}
          <div className="flex-1 min-h-0 p-2">{panel}</div>
        </aside>
      )}
      {/* 데스크톱: 접힘 시 우측 가장자리 재열기 탭 */}
      {!open && (
        <button onClick={() => setOpen(true)} title="AI 상담 열기"
          className="hidden lg:flex fixed right-0 top-1/2 -translate-y-1/2 z-40 flex-col items-center gap-1 rounded-l-xl bg-[#F97316] px-2 py-3 text-white shadow-lg hover:bg-[#EA580C] transition-colors">
          <span className="text-base leading-none">🤖</span>
          <span className="text-[10px] font-bold [writing-mode:vertical-rl]">AI 상담</span>
        </button>
      )}

      {/* ── 모바일: 오버레이 패널 + 플로팅 버튼 ── */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-[60] flex flex-col bg-white">
          <div className="h-1 bg-[#F97316] shrink-0" />
          {header}
          <div className="flex-1 min-h-0 p-2">{panel}</div>
        </div>
      )}
      <button onClick={() => setOpen((v) => !v)} title="AI 상담"
        className="lg:hidden fixed bottom-20 right-4 z-[70] flex items-center gap-2 rounded-full bg-[#F97316] px-4 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-[#EA580C] transition-colors">
        <span className="text-base leading-none">🤖</span>
        <span className="hidden sm:inline">{open ? "닫기" : "AI 상담"}</span>
      </button>
    </>
  );
}
