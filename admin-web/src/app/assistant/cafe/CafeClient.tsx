"use client";
/** /assistant/cafe — 네이버 카페 수집 + AI 분석 (탭별 모듈 셸)
 *
 * 각 탭은 독립 모듈(tabs/*). 최초 방문 시 mount → 이후 유지(hidden)하여
 * 상태 보존(AI GPT 재호출 방지). 탭 추가/수정은 해당 탭 파일만 건드리면 됨.
 */
import { useState } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { type Tab } from "./cafeShared";
import { SummaryTab } from "./tabs/SummaryTab";
import { MyCafesTab } from "./tabs/MyCafesTab";
import { ArticlesTab } from "./tabs/ArticlesTab";
import { AiAnalysisTab } from "./tabs/AiAnalysisTab";
import { ReportTab } from "./tabs/ReportTab";

const TABS: { id: Tab; label: string }[] = [
  { id: "summary",  label: "수집 현황" },
  { id: "my-cafes", label: "내 카페 목록" },
  { id: "articles", label: "수집 게시글" },
  { id: "ai",       label: "AI 분석" },
  { id: "report",   label: "분석 보고서" },
];

export function CafeClient() {
  const [tab, setTab] = useState<Tab>("summary");
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set<Tab>(["summary"]));

  const show = (t: Tab) => {
    setTab(t);
    setVisited((v) => (v.has(t) ? v : new Set(v).add(t)));
  };

  return (
    <PageShell title="카페 탐색" description="네이버 카페 수집 · AI 분석" chatDomain="naver">
      <div className="space-y-4">
        <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-lg font-bold text-[#111827]">네이버 카페</span>
            <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-2 py-0.5 rounded font-semibold">수집 · 분석</span>
          </div>

          <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
            {TABS.map((t) => (
              <button key={t.id} onClick={() => show(t.id)}
                className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                  tab === t.id ? "border-[#1D4ED8] text-[#1D4ED8] font-semibold" : "border-transparent text-[#6B7280] hover:text-[#111827]"
                }`}>
                {t.label}
              </button>
            ))}
          </div>

          {visited.has("summary")  && <div className={tab === "summary"  ? "" : "hidden"}><SummaryTab /></div>}
          {visited.has("my-cafes") && <div className={tab === "my-cafes" ? "" : "hidden"}><MyCafesTab /></div>}
          {visited.has("articles") && <div className={tab === "articles" ? "" : "hidden"}><ArticlesTab /></div>}
          {visited.has("ai")       && <div className={tab === "ai"       ? "" : "hidden"}><AiAnalysisTab /></div>}
          {visited.has("report")   && <div className={tab === "report"   ? "" : "hidden"}><ReportTab /></div>}
        </div>
      </div>
    </PageShell>
  );
}
