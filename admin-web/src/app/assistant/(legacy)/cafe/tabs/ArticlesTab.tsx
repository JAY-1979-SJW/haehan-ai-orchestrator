"use client";
/** 카페 탭 — 수집 게시글 (카테고리 필터 + 페이지네이션) */
import { useState, useEffect, useCallback } from "react";
import { getCafeArticles, type CafeArticle } from "@/lib/assistant/api";
import { CATEGORIES, CAT_COLOR, confidenceBadge } from "../cafeShared";

export function ArticlesTab() {
  const [articles, setArticles] = useState<CafeArticle[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState("");

  const load = useCallback(async (off = 0, cat = category) => {
    setLoading(true); setError(null);
    try {
      const r = await getCafeArticles(50, off, cat || undefined);
      setArticles(r.items); setTotal(r.total); setOffset(off); setSource(r.source_file);
    }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, [category]);

  useEffect(() => { load(0); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center flex-wrap">
        <select value={category}
          onChange={(e) => { setCategory(e.target.value); load(0, e.target.value); }}
          className="border border-[#E5E7EB] rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D4ED8]">
          <option value="">전체 카테고리</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button onClick={() => load(0)} disabled={loading}
          className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
        <span className="text-xs text-[#9CA3AF]">총 {total.toLocaleString()}건 {source && `· ${source}`}</span>
      </div>
      {error && <p className="text-xs text-[#DC2626]">오류: {error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB]">
              {["카테고리", "유형", "제목", "날짜", "조회", "신뢰도"].map((h) => (
                <th key={h} className="text-left py-2 px-2 text-[#6B7280] font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E5E7EB]">
            {articles.map((a) => (
              <tr key={a.article_id} className="hover:bg-[#F9FAFB]">
                <td className="py-2 px-2 whitespace-nowrap">
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${CAT_COLOR[a.category] ?? CAT_COLOR["기타"]}`}>{a.category}</span>
                </td>
                <td className="py-2 px-2 text-[#6B7280] whitespace-nowrap">{a.type}</td>
                <td className="py-2 px-2 max-w-xs">
                  <a href={a.href} target="_blank" rel="noopener noreferrer"
                    className="text-[#1D4ED8] hover:underline line-clamp-1">{a.title}</a>
                </td>
                <td className="py-2 px-2 text-[#9CA3AF] whitespace-nowrap">{a.date}</td>
                <td className="py-2 px-2 text-[#6B7280] text-right">{Number(a.view_count).toLocaleString()}</td>
                <td className="py-2 px-2">
                  <span className={`px-1.5 py-0.5 rounded border text-xs ${confidenceBadge(a.confidence)}`}>{a.confidence}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2 justify-end">
        <button disabled={offset === 0 || loading} onClick={() => load(Math.max(0, offset - 50))}
          className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg disabled:opacity-40">← 이전</button>
        <span className="text-xs text-[#6B7280] flex items-center">
          {offset + 1}–{Math.min(offset + 50, total)} / {total.toLocaleString()}
        </span>
        <button disabled={offset + 50 >= total || loading} onClick={() => load(offset + 50)}
          className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg disabled:opacity-40">다음 →</button>
      </div>
    </div>
  );
}
