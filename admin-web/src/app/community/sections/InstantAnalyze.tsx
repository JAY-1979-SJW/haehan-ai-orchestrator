"use client";
/** 커뮤니티 레이더 — 사이트 링크 바로 분석 (등록 없이 원샷) */
import { useState } from "react";

export function InstantAnalyze({ onAnalyze, analyzingUrl }: {
  onAnalyze: (url: string, label: string) => void;
  analyzingUrl: string | null;
}) {
  const [instantUrl, setInstantUrl] = useState("");
  const run = () => { const u = instantUrl.trim(); if (u) onAnalyze(u, u); };

  return (
    <div className="border border-[#DBEAFE] bg-[#F8FAFF] rounded-2xl p-4 space-y-2">
      <p className="text-sm font-bold text-[#1D4ED8]">🔗 사이트 링크 바로 분석</p>
      <div className="flex flex-wrap gap-2">
        <input value={instantUrl} onChange={(e) => setInstantUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="https://... 사이트 링크 붙여넣기 (게시판·블로그·뉴스 등)"
          className="flex-1 min-w-[260px] border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#1D4ED8]" />
        <button onClick={run} disabled={!instantUrl.trim() || analyzingUrl === instantUrl.trim()}
          className="px-4 py-2 rounded-xl bg-[#1D4ED8] text-white text-sm font-semibold hover:bg-[#1E40AF] disabled:opacity-40">
          {analyzingUrl === instantUrl.trim() ? "분석 중…" : "⚡ 바로 분석"}
        </button>
      </div>
      <p className="text-[11px] text-[#9CA3AF]">등록 없이 즉시 — 로컬 브라우저(로그인 세션 사용)로 글을 수집하고 AI가 흐름·수익기회를 분석합니다. 결과는 아래에 표시됩니다.</p>
    </div>
  );
}
