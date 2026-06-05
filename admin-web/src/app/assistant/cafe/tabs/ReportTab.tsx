"use client";
/** 카페 탭 — 분석 보고서 (규칙기반 카테고리 통계) */
import { useState, useEffect, useCallback } from "react";
import { getCafeKB, type CafeKB } from "@/lib/assistant/api";
import { CAT_COLOR } from "../cafeShared";
import { CategoryCard } from "../CategoryCard";

export function ReportTab() {
  const [kb, setKb] = useState<CafeKB | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setKb(await getCafeKB()); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={load} disabled={loading}
          className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
        {kb && (
          <div className="flex gap-3 text-xs text-[#6B7280]">
            <span>총 <b className="text-[#111827]">{kb.total.toLocaleString()}</b>건 분석</span>
            <span>카테고리 <b className="text-[#111827]">{kb.categories.length}</b>개</span>
            <span className="text-[#9CA3AF]">{kb.source_file}</span>
          </div>
        )}
      </div>
      <p className="text-[11px] text-[#9CA3AF]">키워드 규칙 기반 카테고리 통계입니다. 카페 주제에 맞는 흐름·수익기회는 [AI 분석] 탭을 보세요.</p>
      {error && <p className="text-xs text-[#DC2626]">오류: {error}</p>}

      {kb && (
        <>
          <div className="grid grid-cols-4 gap-3">
            {kb.categories.map((s) => (
              <div key={s.category} className={`rounded-lg p-3 border ${CAT_COLOR[s.category] ?? CAT_COLOR["기타"]}`}>
                <p className="text-xs font-semibold">{s.category}</p>
                <p className="text-lg font-bold">{s.total.toLocaleString()}<span className="text-xs font-normal ml-1">건</span></p>
                <p className="text-xs opacity-75">질문 {s.question_count.toLocaleString()}건 · 조회 {s.total_views.toLocaleString()}</p>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            {kb.categories.map((s) => (
              <CategoryCard key={s.category} s={s} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
