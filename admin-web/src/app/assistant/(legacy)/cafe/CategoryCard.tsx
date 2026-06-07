"use client";
/** 분석 보고서 — 카테고리별 상세 아코디언 카드 */
import { useState } from "react";
import { type CafeCategorySummary } from "@/lib/assistant/api";
import { CAT_COLOR } from "./cafeShared";

export function CategoryCard({ s }: { s: CafeCategorySummary }) {
  const [open, setOpen] = useState(false);
  const color = CAT_COLOR[s.category] ?? CAT_COLOR["기타"];

  return (
    <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[#F9FAFB] transition-colors text-left"
      >
        <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${color}`}>
          {s.category}
        </span>
        <div className="flex gap-4 text-xs text-[#6B7280] flex-1">
          <span>총 <b className="text-[#111827]">{s.total.toLocaleString()}</b>건</span>
          <span>질문 <b className="text-[#111827]">{s.question_count.toLocaleString()}</b>건</span>
          <span>총조회 <b className="text-[#111827]">{s.total_views.toLocaleString()}</b></span>
          <span>질문평균 <b className="text-[#111827]">{s.avg_question_views}</b>회</span>
        </div>
        <span className="text-[#9CA3AF] text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-[#E5E7EB] px-4 py-4 space-y-4 bg-white">
          {s.keywords.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-[#6B7280] mb-2">🔑 핵심 키워드</p>
              <div className="flex flex-wrap gap-1.5">
                {s.keywords.slice(0, 15).map((k) => (
                  <span key={k.word}
                    className="text-xs bg-[#F3F4F6] text-[#374151] px-2 py-0.5 rounded-full border border-[#E5E7EB]">
                    {k.word} <span className="text-[#9CA3AF]">({k.count})</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {s.top_questions.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-[#6B7280] mb-2">📌 조회수 상위 질문</p>
              <div className="space-y-1">
                {s.top_questions.slice(0, 7).map((q, i) => (
                  <div key={i} className="flex items-baseline gap-2">
                    <span className="text-xs text-[#9CA3AF] w-5 text-right shrink-0">{i + 1}.</span>
                    <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-1.5 py-0.5 rounded shrink-0">
                      {Number(q.views).toLocaleString()}회
                    </span>
                    <a href={q.href} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-[#111827] hover:text-[#1D4ED8] hover:underline line-clamp-1">
                      {q.title}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          {s.question_clusters.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-[#6B7280] mb-2">🔗 반복 질문 군집</p>
              <div className="space-y-2">
                {s.question_clusters.slice(0, 6).map((c, i) => (
                  <div key={i} className="bg-[#F9FAFB] rounded-lg px-3 py-2 border border-[#E5E7EB]">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-1.5 py-0.5 rounded shrink-0">
                        {c.size}건 / {c.total_views.toLocaleString()}조회
                      </span>
                      <a href={c.rep_href} target="_blank" rel="noopener noreferrer"
                        className="text-xs font-medium text-[#111827] hover:underline line-clamp-1">
                        {c.topic}
                      </a>
                    </div>
                    {c.similar.length > 0 && (
                      <div className="mt-1 pl-2 space-y-0.5">
                        {c.similar.slice(0, 3).map((sim, j) => (
                          <p key={j} className="text-xs text-[#6B7280] line-clamp-1">└ {sim}</p>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
