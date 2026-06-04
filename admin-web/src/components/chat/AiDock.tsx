"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import SmartStoreChat from "@/app/naver/smartstore/SmartStoreChat";
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

/** 전 화면 하단 고정 AI 상담 독. 보는 화면(도메인)에 맞춰 연동. */
export function AiDock() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname() ?? "";

  if (HIDE_PREFIXES.some((p) => pathname.startsWith(p))) return null;

  const domain = domainFromPath(pathname);
  const isSmartstore = domain === "smartstore";

  return (
    <>
      {/* 펼침 패널 */}
      {open && (
        <div
          className="fixed bottom-[140px] lg:bottom-[76px] right-4 z-[60] flex flex-col overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-2xl"
          style={{ width: "min(440px, calc(100vw - 2rem))", height: "min(560px, 72vh)" }}
        >
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#F3F4F6] bg-[#FFF7ED] shrink-0">
            <span className="text-xs font-bold text-[#C2410C]">
              🤖 AI 상담 {isSmartstore ? "· 스마트스토어" : `· ${domain}`}
            </span>
            <button
              onClick={() => setOpen(false)}
              className="text-[#9CA3AF] hover:text-[#111827] text-sm px-1"
              title="닫기"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 min-h-0 p-2">
            {isSmartstore ? (
              <SmartStoreChat />
            ) : (
              <UniversalChat domain={domain} title="AI 어시스턴트" className="h-full rounded-xl" />
            )}
          </div>
        </div>
      )}

      {/* 하단 고정 토글 버튼 */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-20 lg:bottom-4 right-4 z-[60] flex items-center gap-2 rounded-full bg-[#F97316] px-4 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-[#EA580C] transition-colors"
        title="AI 상담 열기"
      >
        <span className="text-base leading-none">🤖</span>
        <span className="hidden sm:inline">{open ? "AI 상담 닫기" : "AI 상담"}</span>
      </button>
    </>
  );
}
