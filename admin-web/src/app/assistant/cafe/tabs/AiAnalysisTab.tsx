"use client";
/** 카페 탭 — AI 분석 (탭 열면 자동 분석, 1회) */
import { useState, useEffect, useCallback } from "react";
import { type AiReport } from "../cafeShared";

export function AiAnalysisTab() {
  const [report, setReport] = useState<AiReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
      const r = await fetch(`/api/proxy/api/v1/naver-cafe/ai-analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ max_posts: 500 }),
      });
      const d = await r.json();
      if (d.ok) setReport(d as AiReport);
      else setError(d.detail || d.error || "AI 분석 실패");
    } catch (e) { setError(e instanceof Error ? e.message : "AI 분석 실패"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { run(); }, [run]); // 탭 최초 마운트 시 1회 자동 분석

  return (
    <div className="space-y-4">
      <div className="border border-[#DBEAFE] bg-[#F8FAFF] rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-bold text-[#1D4ED8]">🤖 AI 분석 — 흐름·수익기회</span>
          <button onClick={run} disabled={loading}
            className="px-3 py-1.5 bg-[#1D4ED8] text-white text-xs rounded-lg font-semibold disabled:opacity-50">
            {loading ? "분석 중… (10~30초)" : "다시 분석"}
          </button>
          {report && (
            <span className="text-[11px] text-[#6B7280] ml-auto">
              전체 {report.total_collected?.toLocaleString()}건 중 조회수 상위 {report.post_count}건 분석
            </span>
          )}
        </div>
        <p className="text-[11px] text-[#9CA3AF]">수집한 카페 글을 AI가 읽고 지금의 흐름과 수익 기회를 정리합니다. (수집 게시글이 있으면 탭 열 때 자동 분석)</p>
        {error && <p className="text-xs text-[#DC2626]">오류: {error}</p>}
        {loading && !report && <p className="text-xs text-[#6B7280]">수집 글을 분석하는 중입니다…</p>}

        {report && (
          <div className="space-y-3">
            {report.summary && (
              <div className="bg-white rounded-lg border border-[#E5E7EB] p-3">
                <p className="text-xs font-semibold text-[#6B7280] mb-1">📋 전체 흐름</p>
                <p className="text-sm text-[#111827]">{report.summary}</p>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {report.trends?.length > 0 && (
                <div className="bg-white rounded-lg border border-[#E5E7EB] p-3">
                  <p className="text-xs font-semibold text-[#6B7280] mb-2">🔥 지금 뜨는 흐름</p>
                  <ul className="space-y-1">
                    {report.trends.map((t, i) => (
                      <li key={i} className="text-xs text-[#111827] flex gap-1.5"><span className="text-[#1D4ED8]">•</span>{t}</li>
                    ))}
                  </ul>
                </div>
              )}
              {report.topics?.length > 0 && (
                <div className="bg-white rounded-lg border border-[#E5E7EB] p-3">
                  <p className="text-xs font-semibold text-[#6B7280] mb-2">🧩 주요 토픽 비중</p>
                  <div className="flex flex-wrap gap-1.5">
                    {report.topics.map((tp, i) => (
                      <span key={i} className="text-xs bg-[#F3F4F6] text-[#374151] px-2 py-0.5 rounded-full border border-[#E5E7EB]">
                        {tp.name} <span className="text-[#9CA3AF]">({tp.share})</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {report.opportunities?.length > 0 && (
              <div className="bg-white rounded-lg border border-[#BBF7D0] p-3">
                <p className="text-xs font-semibold text-[#16A34A] mb-2">💰 수익 기회</p>
                <div className="space-y-2">
                  {report.opportunities.map((o, i) => (
                    <div key={i} className="bg-[#F0FDF4] rounded-lg px-3 py-2 border border-[#BBF7D0]">
                      <p className="text-sm font-medium text-[#111827]">{o.idea}</p>
                      <p className="text-xs text-[#6B7280] mt-0.5">{o.why}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {report.actions?.length > 0 && (
              <div className="bg-white rounded-lg border border-[#FED7AA] p-3">
                <p className="text-xs font-semibold text-[#C2410C] mb-2">✅ 바로 해볼 액션</p>
                <ul className="space-y-1">
                  {report.actions.map((a, i) => (
                    <li key={i} className="text-xs text-[#111827] flex gap-1.5"><span className="text-[#C2410C]">{i + 1}.</span>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
