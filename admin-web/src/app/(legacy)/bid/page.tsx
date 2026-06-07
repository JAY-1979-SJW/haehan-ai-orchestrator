"use client";
import { useState, useCallback } from "react";
import Link from "next/link";
import { PageShell } from "@/components/ui/PageShell";

const BID_API = "https://bid.haehan-ai.kr/api/v1";
const BID_BASE = "https://bid.haehan-ai.kr";

// ── 공종 목록 ─────────────────────────────────────────────────────────────────
const TRADES = [
  { label: "전체",       value: "" },
  { label: "소방",       value: "소방" },
  { label: "전기",       value: "전기" },
  { label: "통신",       value: "통신" },
  { label: "건축",       value: "건축" },
  { label: "토목",       value: "토목" },
  { label: "기계설비",   value: "기계설비" },
  { label: "조경",       value: "조경" },
  { label: "정보통신",   value: "정보통신" },
];

// ── 빠른 버튼 ─────────────────────────────────────────────────────────────────
const QUICK = [
  { label: "소방 공고",   trade: "소방",     color: "#DC2626", bg: "#FEF2F2", border: "#FECACA" },
  { label: "전기 공고",   trade: "전기",     color: "#F97316", bg: "#FFF7ED", border: "#FED7AA" },
  { label: "통신 공고",   trade: "통신",     color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE" },
  { label: "건축 공고",   trade: "건축",     color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE" },
  { label: "토목 공고",   trade: "토목",     color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
  { label: "전체 공고",   trade: "",         color: "#374151", bg: "#F9FAFB", border: "#E5E7EB" },
];

// ── 금액 포맷 ─────────────────────────────────────────────────────────────────
function fmtPrice(v: number | null): string {
  if (!v) return "-";
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}억`;
  if (v >= 10_000_000) return `${(v / 100_000_000).toFixed(2)}억`;
  if (v >= 10_000) return `${Math.round(v / 10_000)}만`;
  return v.toLocaleString();
}

function fmtDate(s: string | null): string {
  if (!s) return "-";
  return s.slice(0, 10);
}

// ── 공고 행 ───────────────────────────────────────────────────────────────────
interface Notice {
  bid_ntce_no: string;
  bid_ntce_nm: string;
  dminstt_nm: string;
  openg_dt: string;
  bid_clse_dt: string;
  presmpt_prce: number | null;
  trade: string;
  bid_status: string | null;
  open_status: string;
  competition_type: string | null;
  license_status: string;
}

const TRADE_COLOR: Record<string, string> = {
  "소방시설": "#DC2626", "소방": "#DC2626",
  "전기":     "#F97316",
  "통신":     "#7C3AED",
  "건축":     "#1D4ED8",
  "토목":     "#16A34A",
  "기계설비": "#0891B2",
  "정보통신": "#7C3AED",
};

export default function BidPage() {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trade, setTrade] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  const load = useCallback(async (t: string, kw: string, pg: number) => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ page: String(pg), page_size: "20" });
      if (t) params.set("trade", t);
      if (kw) params.set("search", kw);
      const r = await fetch(`${BID_API}/notices?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setNotices(d.items ?? []);
      setTotal(d.total ?? 0);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const search = (t = trade, kw = keyword, pg = 1) => {
    setTrade(t); setKeyword(kw); setPage(pg);
    load(t, kw, pg);
  };

  return (
    <PageShell title="입찰분석 BID" description="G2B 나라장터 공고 조회 · AI 분석" chatDomain="bid">
      <div className="space-y-4 w-full">

        {/* 헤더 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#111827] flex items-center justify-center text-white text-xs font-bold">BID</div>
              <div>
                <p className="text-sm font-bold text-[#111827]">해한AI 입찰분석</p>
                <a href={BID_BASE} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-[#6B7280] hover:text-[#F97316] transition-colors">
                  bid.haehan-ai.kr →
                </a>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {total !== null && (
                <span className="text-xs text-[#9CA3AF]">
                  총 <span className="font-bold text-[#111827]">{total.toLocaleString()}</span>건
                </span>
              )}
              <a href={BID_BASE} target="_blank" rel="noopener noreferrer"
                className="px-3 py-1.5 rounded-lg bg-[#111827] text-white text-xs font-semibold hover:bg-[#374151] transition-colors">
                BID 앱 열기 →
              </a>
            </div>
          </div>
        </div>

        {/* 빠른 버튼 */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {QUICK.map((q) => (
            <button key={q.label}
              onClick={() => search(q.trade, "", 1)}
              className="py-2.5 px-3 rounded-xl border text-xs font-semibold transition-all hover:shadow-sm text-center"
              style={{ background: q.bg, borderColor: q.border, color: q.color }}>
              {q.label}
            </button>
          ))}
        </div>

        {/* 검색 바 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-4 flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[160px]">
            <label className="block text-xs font-medium text-[#374151] mb-1">공종</label>
            <select value={trade} onChange={(e) => setTrade(e.target.value)}
              className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#111827]">
              {TRADES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div className="flex-[2] min-w-[200px]">
            <label className="block text-xs font-medium text-[#374151] mb-1">공고명 검색</label>
            <input value={keyword} onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="공고명, 발주기관 입력..."
              className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#111827]" />
          </div>
          <button onClick={() => search()} disabled={loading}
            className="px-5 py-2 rounded-xl bg-[#111827] text-white text-sm font-semibold hover:bg-[#374151] disabled:opacity-40 transition-colors">
            {loading ? "조회 중..." : "검색"}
          </button>
        </div>

        {/* 결과 테이블 */}
        {error && (
          <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl px-4 py-3 text-sm text-[#DC2626]">{error}</div>
        )}

        {notices.length > 0 && (
          <div className="bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                  <tr>
                    {["공고명", "발주기관", "공종", "추정가격", "개찰일", "마감일", "상태", "상세"].map((h) => (
                      <th key={h} className="text-left text-[#6B7280] font-semibold px-4 py-3 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {notices.map((n, i) => {
                    const tradeColor = TRADE_COLOR[n.trade] ?? "#374151";
                    return (
                      <tr key={`${n.bid_ntce_no}-${i}`}
                        className="border-b border-[#F3F4F6] hover:bg-[#F9FAFB] transition-colors">
                        <td className="px-4 py-3 max-w-[280px]">
                          <p className="font-medium text-[#111827] line-clamp-2 leading-snug">{n.bid_ntce_nm}</p>
                        </td>
                        <td className="px-4 py-3 text-[#6B7280] whitespace-nowrap max-w-[120px] truncate">{n.dminstt_nm}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                            style={{ background: tradeColor + "18", color: tradeColor }}>
                            {n.trade || "-"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[#374151] whitespace-nowrap">
                          {fmtPrice(n.presmpt_prce)}
                        </td>
                        <td className="px-4 py-3 text-[#6B7280] whitespace-nowrap">{fmtDate(n.openg_dt)}</td>
                        <td className="px-4 py-3 text-[#6B7280] whitespace-nowrap">{fmtDate(n.bid_clse_dt)}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            n.open_status === "미개찰" ? "bg-[#F0FDF4] text-[#16A34A]" :
                            n.bid_status === "CANCELLED" ? "bg-[#FEF2F2] text-[#DC2626]" :
                            "bg-[#F9FAFB] text-[#6B7280]"
                          }`}>
                            {n.open_status || n.bid_status || "-"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <a href={`${BID_BASE}/bids/${n.bid_ntce_no}`} target="_blank" rel="noopener noreferrer"
                            className="text-[#F97316] font-semibold hover:underline whitespace-nowrap">
                            AI 분석 →
                          </a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* 페이지네이션 */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-[#E5E7EB]">
              <p className="text-xs text-[#9CA3AF]">
                {total?.toLocaleString()}건 중 {(page - 1) * 20 + 1}–{Math.min(page * 20, total ?? 0)}
              </p>
              <div className="flex gap-2">
                <button disabled={page <= 1 || loading}
                  onClick={() => search(trade, keyword, page - 1)}
                  className="px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-xs text-[#374151] hover:border-[#111827] disabled:opacity-40 transition-colors">
                  ← 이전
                </button>
                <span className="px-3 py-1.5 text-xs text-[#374151]">p.{page}</span>
                <button disabled={loading || page * 20 >= (total ?? 0)}
                  onClick={() => search(trade, keyword, page + 1)}
                  className="px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-xs text-[#374151] hover:border-[#111827] disabled:opacity-40 transition-colors">
                  다음 →
                </button>
              </div>
            </div>
          </div>
        )}

        {!loading && notices.length === 0 && total === null && (
          <div className="bg-white border border-[#E5E7EB] rounded-2xl py-16 text-center">
            <p className="text-3xl mb-3">📋</p>
            <p className="text-sm font-medium text-[#6B7280]">공종 버튼을 클릭하거나 검색하세요</p>
            <p className="text-xs text-[#9CA3AF] mt-1">나라장터 전체 공고 {(237917).toLocaleString()}건 이상</p>
          </div>
        )}

      </div>
    </PageShell>
  );
}
