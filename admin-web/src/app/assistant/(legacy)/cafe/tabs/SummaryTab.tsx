"use client";
/** 카페 탭 — 수집 현황 */
import { useState, useEffect, useCallback } from "react";
import { getCafeSummary, type CafeSummary } from "@/lib/assistant/api";

export function SummaryTab() {
  const [summary, setSummary] = useState<CafeSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setSummary(await getCafeSummary()); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-3">
      <button onClick={load} disabled={loading}
        className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
        {loading ? "불러오는 중…" : "새로고침"}
      </button>
      {error && <p className="text-xs text-[#DC2626]">오류: {error}</p>}
      {summary && (
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "가입 카페",   value: `${summary.my_cafes_count}개`,                           sub: null },
            { label: "수집 게시글", value: `${summary.latest_raw_count.toLocaleString()}건`,         sub: summary.latest_raw_file },
            { label: "분류 게시글", value: `${summary.latest_classified_count.toLocaleString()}건`,  sub: summary.latest_classified_file },
            { label: "분석 보고서", value: summary.has_report ? "있음 ✓" : "없음",                   sub: summary.latest_report_file },
          ].map((card) => (
            <div key={card.label} className="border border-[#E5E7EB] rounded-lg p-3">
              <p className="text-xs text-[#6B7280]">{card.label}</p>
              <p className="text-xl font-bold text-[#111827]">{card.value}</p>
              {card.sub && <p className="text-xs text-[#9CA3AF] truncate mt-0.5">{card.sub}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
