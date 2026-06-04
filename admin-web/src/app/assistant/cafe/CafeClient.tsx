"use client";
/** /assistant/cafe — 네이버 카페 수집 + 수집 내용 AI 분석 (read-only) */
import { useState, useCallback, useEffect } from "react";
import { PageShell } from "@/components/ui/PageShell";
import {
  getCafeSummary, getMyCafes, getCafeArticles,
  type MyCafe, type CafeArticle, type CafeSummary,
} from "@/lib/assistant/api";

type Tab = "summary" | "my-cafes" | "articles" | "report";

export function CafeClient() {
  const [tab, setTab] = useState<Tab>("summary");

  const [summary, setSummary] = useState<CafeSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [cafes, setCafes] = useState<MyCafe[]>([]);
  const [cafesLoading, setCafesLoading] = useState(false);
  const [cafesError, setCafesError] = useState<string | null>(null);

  const [articles, setArticles] = useState<CafeArticle[]>([]);
  const [artTotal, setArtTotal] = useState(0);
  const [artOffset, setArtOffset] = useState(0);
  const [artLoading, setArtLoading] = useState(false);
  const [artError, setArtError] = useState<string | null>(null);
  const [artSource, setArtSource] = useState("");

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true); setSummaryError(null);
    try { setSummary(await getCafeSummary()); }
    catch (e: unknown) { setSummaryError(e instanceof Error ? e.message : String(e)); }
    finally { setSummaryLoading(false); }
  }, []);

  const loadCafes = useCallback(async () => {
    setCafesLoading(true); setCafesError(null);
    try { const r = await getMyCafes(); setCafes(r.cafes); }
    catch (e: unknown) { setCafesError(e instanceof Error ? e.message : String(e)); }
    finally { setCafesLoading(false); }
  }, []);

  // ── 수집 (CDP, 네이버 로그인) ──────────────────────────────────────────────
  const [collectingCafes, setCollectingCafes] = useState(false);
  const [collectingUrl, setCollectingUrl] = useState<string | null>(null);
  const [collectMsg, setCollectMsg] = useState<string | null>(null);
  const [collectDays, setCollectDays] = useState(90); // 수집 기간(일). 3650=전체

  const apiPost = async (path: string, body: unknown) => {
    const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
    const r = await fetch(`/api/proxy${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
      body: JSON.stringify(body),
    });
    return r.json();
  };

  // ── AI 분석 보고 ──────────────────────────────────────────────────────────
  type AiReport = {
    ok: boolean; summary: string; trends: string[];
    opportunities: { idea: string; why: string }[];
    topics: { name: string; share: string }[];
    actions: string[]; post_count: number; total_collected: number;
  };
  const [aiReport, setAiReport] = useState<AiReport | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const runAiAnalyze = useCallback(async () => {
    setAiLoading(true); setAiError(null);
    try {
      const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
      const r = await fetch(`/api/proxy/api/v1/naver-cafe/ai-analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ max_posts: 500 }),
      });
      const d = await r.json();
      if (d.ok) setAiReport(d as AiReport);
      else setAiError(d.detail || d.error || "AI 분석 실패");
    } catch (e) { setAiError(e instanceof Error ? e.message : "AI 분석 실패"); }
    finally { setAiLoading(false); }
  }, []);

  const handleCollectMyCafes = async () => {
    setCollectingCafes(true); setCollectMsg(null); setCafesError(null);
    try {
      const d = await apiPost("/api/v1/naver-cafe/collect-my-cafes", {});
      if (d.ok) { setCafes(d.cafes || []); setCollectMsg(`내 카페 ${d.count}개 수집 완료`); }
      else setCafesError(d.detail || d.error || "수집 실패");
    } catch (e) { setCafesError(e instanceof Error ? e.message : "수집 실패"); }
    finally { setCollectingCafes(false); }
  };

  const handleCollectArticles = async (cafe: MyCafe) => {
    const url = cafe.href || `https://cafe.naver.com/${cafe.cafe_id}`;
    setCollectingUrl(cafe.cafe_id); setCollectMsg(`${cafe.cafe_name || cafe.cafe_id} 수집 중… (1~2분)`);
    try {
      const d = await apiPost("/api/v1/naver-cafe/collect", { cafe_url: url, days: collectDays });
      if (d.ok) { setCollectMsg(`${cafe.cafe_name || cafe.cafe_id} — 게시글 ${d.collected}건 수집 완료`); loadSummary(); }
      else setCollectMsg(`수집 실패: ${d.detail || d.error || ""}`);
    } catch (e) { setCollectMsg(`수집 실패: ${e instanceof Error ? e.message : ""}`); }
    finally { setCollectingUrl(null); }
  };

  const loadArticles = useCallback(async (offset = 0) => {
    setArtLoading(true); setArtError(null);
    try {
      const r = await getCafeArticles(50, offset);
      setArticles(r.items); setArtTotal(r.total); setArtOffset(offset); setArtSource(r.source_file);
    }
    catch (e: unknown) { setArtError(e instanceof Error ? e.message : String(e)); }
    finally { setArtLoading(false); }
  }, []);

  useEffect(() => {
    if (tab === "summary" && !summary) loadSummary();
    if (tab === "my-cafes" && cafes.length === 0) loadCafes();
    if (tab === "articles" && articles.length === 0) loadArticles(0);
    if (tab === "report" && !aiReport && !aiLoading) runAiAnalyze();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const TABS: { id: Tab; label: string }[] = [
    { id: "summary",  label: "수집 현황" },
    { id: "my-cafes", label: "내 카페 목록" },
    { id: "articles", label: "수집 게시글" },
    { id: "report",   label: "AI 분석" },
  ];

  const confidenceBadge = (c: string) => ({
    high:   "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
    medium: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
    low:    "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
  }[c] ?? "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]");

  return (
    <PageShell title="카페 탐색" description="네이버 카페 수집 · AI 분석" chatDomain="naver">
      <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">네이버 카페</span>
          <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-2 py-0.5 rounded font-semibold">수집 · AI 분석</span>
        </div>

        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id ? "border-[#1D4ED8] text-[#1D4ED8] font-semibold" : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 수집 현황 ── */}
        {tab === "summary" && (
          <div className="space-y-3">
            <button onClick={loadSummary} disabled={summaryLoading}
              className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
              {summaryLoading ? "불러오는 중…" : "새로고침"}
            </button>
            {summaryError && <p className="text-xs text-[#DC2626]">오류: {summaryError}</p>}
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
        )}

        {/* ── 내 카페 목록 ── */}
        {tab === "my-cafes" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={handleCollectMyCafes} disabled={collectingCafes}
                className="px-3 py-1.5 bg-[#03C75A] text-white text-xs rounded-lg font-semibold disabled:opacity-50">
                {collectingCafes ? "수집 중…" : "📥 내 카페 수집"}
              </button>
              <button onClick={loadCafes} disabled={cafesLoading}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
                {cafesLoading ? "불러오는 중…" : "새로고침"}
              </button>
              <div className="flex items-center gap-1.5 ml-auto">
                <span className="text-[11px] text-[#6B7280]">수집 기간</span>
                <select value={collectDays} onChange={(e) => setCollectDays(Number(e.target.value))}
                  className="border border-[#E5E7EB] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-[#1D4ED8]">
                  <option value={7}>최근 1주</option>
                  <option value={30}>최근 1개월</option>
                  <option value={90}>최근 3개월</option>
                  <option value={180}>최근 6개월</option>
                  <option value={365}>최근 1년</option>
                  <option value={3650}>전체 기간</option>
                </select>
              </div>
            </div>
            <p className="text-[11px] text-[#9CA3AF]">[내 카페 수집]으로 가입 카페를 가져온 뒤, 각 카페의 [게시글 수집]을 누르세요. 수집 기간을 먼저 고르세요(게시판 구분 없이 전체글 수집). (네이버 로그인 필요)</p>
            {collectMsg && <p className="text-xs text-[#16A34A]">{collectMsg}</p>}
            {cafesError && <p className="text-xs text-[#DC2626]">오류: {cafesError}</p>}
            <div className="divide-y divide-[#E5E7EB]">
              {cafes.map((c, i) => (
                <div key={c.cafe_id} className="flex items-center gap-3 py-2">
                  <span className="text-xs text-[#9CA3AF] w-6 text-right">{i + 1}</span>
                  <a href={c.href} target="_blank" rel="noopener noreferrer"
                    className="flex-1 text-sm text-[#1D4ED8] hover:underline font-medium truncate">
                    {c.cafe_name || c.cafe_id}
                  </a>
                  {c.member_count > 0 && <span className="text-xs text-[#6B7280]">{c.member_count.toLocaleString()}명</span>}
                  <button onClick={() => handleCollectArticles(c)} disabled={collectingUrl === c.cafe_id}
                    className="px-2.5 py-1 rounded-lg border border-[#03C75A] text-[#03C75A] text-[11px] font-semibold hover:bg-[#F0FDF4] disabled:opacity-40 shrink-0">
                    {collectingUrl === c.cafe_id ? "수집 중…" : "게시글 수집"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── 수집 게시글 ── */}
        {tab === "articles" && (
          <div className="space-y-3">
            <div className="flex gap-2 items-center flex-wrap">
              <button onClick={() => loadArticles(0)} disabled={artLoading}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
                {artLoading ? "불러오는 중…" : "새로고침"}
              </button>
              <span className="text-xs text-[#9CA3AF]">총 {artTotal.toLocaleString()}건 {artSource && `· ${artSource}`}</span>
            </div>
            {artError && <p className="text-xs text-[#DC2626]">오류: {artError}</p>}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#E5E7EB]">
                    {["유형","제목","날짜","조회","신뢰도"].map((h) => (
                      <th key={h} className="text-left py-2 px-2 text-[#6B7280] font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E7EB]">
                  {articles.map((a) => (
                    <tr key={a.article_id} className="hover:bg-[#F9FAFB]">
                      <td className="py-2 px-2 text-[#6B7280] whitespace-nowrap">{a.type}</td>
                      <td className="py-2 px-2 max-w-md">
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
              <button disabled={artOffset === 0 || artLoading} onClick={() => loadArticles(Math.max(0, artOffset - 50))}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg disabled:opacity-40">← 이전</button>
              <span className="text-xs text-[#6B7280] flex items-center">
                {artOffset + 1}–{Math.min(artOffset + 50, artTotal)} / {artTotal.toLocaleString()}
              </span>
              <button disabled={artOffset + 50 >= artTotal || artLoading} onClick={() => loadArticles(artOffset + 50)}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg disabled:opacity-40">다음 →</button>
            </div>
          </div>
        )}

        {/* ── AI 분석 ── */}
        {tab === "report" && (
          <div className="space-y-4">
            <div className="border border-[#DBEAFE] bg-[#F8FAFF] rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-bold text-[#1D4ED8]">🤖 AI 분석 — 흐름·수익기회</span>
                <button onClick={runAiAnalyze} disabled={aiLoading}
                  className="px-3 py-1.5 bg-[#1D4ED8] text-white text-xs rounded-lg font-semibold disabled:opacity-50">
                  {aiLoading ? "분석 중… (10~30초)" : "다시 분석"}
                </button>
                {aiReport && (
                  <span className="text-[11px] text-[#6B7280] ml-auto">
                    전체 {aiReport.total_collected?.toLocaleString()}건 중 조회수 상위 {aiReport.post_count}건 분석
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[#9CA3AF]">수집한 카페 글을 AI가 읽고 지금의 흐름과 수익 기회를 정리합니다. (수집 게시글이 있으면 탭 열 때 자동 분석)</p>
              {aiError && <p className="text-xs text-[#DC2626]">오류: {aiError}</p>}
              {aiLoading && !aiReport && <p className="text-xs text-[#6B7280]">수집 글을 분석하는 중입니다…</p>}

              {aiReport && (
                <div className="space-y-3">
                  {aiReport.summary && (
                    <div className="bg-white rounded-lg border border-[#E5E7EB] p-3">
                      <p className="text-xs font-semibold text-[#6B7280] mb-1">📋 전체 흐름</p>
                      <p className="text-sm text-[#111827]">{aiReport.summary}</p>
                    </div>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {aiReport.trends?.length > 0 && (
                      <div className="bg-white rounded-lg border border-[#E5E7EB] p-3">
                        <p className="text-xs font-semibold text-[#6B7280] mb-2">🔥 지금 뜨는 흐름</p>
                        <ul className="space-y-1">
                          {aiReport.trends.map((t, i) => (
                            <li key={i} className="text-xs text-[#111827] flex gap-1.5"><span className="text-[#1D4ED8]">•</span>{t}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {aiReport.topics?.length > 0 && (
                      <div className="bg-white rounded-lg border border-[#E5E7EB] p-3">
                        <p className="text-xs font-semibold text-[#6B7280] mb-2">🧩 주요 토픽 비중</p>
                        <div className="flex flex-wrap gap-1.5">
                          {aiReport.topics.map((tp, i) => (
                            <span key={i} className="text-xs bg-[#F3F4F6] text-[#374151] px-2 py-0.5 rounded-full border border-[#E5E7EB]">
                              {tp.name} <span className="text-[#9CA3AF]">({tp.share})</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  {aiReport.opportunities?.length > 0 && (
                    <div className="bg-white rounded-lg border border-[#BBF7D0] p-3">
                      <p className="text-xs font-semibold text-[#16A34A] mb-2">💰 수익 기회</p>
                      <div className="space-y-2">
                        {aiReport.opportunities.map((o, i) => (
                          <div key={i} className="bg-[#F0FDF4] rounded-lg px-3 py-2 border border-[#BBF7D0]">
                            <p className="text-sm font-medium text-[#111827]">{o.idea}</p>
                            <p className="text-xs text-[#6B7280] mt-0.5">{o.why}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {aiReport.actions?.length > 0 && (
                    <div className="bg-white rounded-lg border border-[#FED7AA] p-3">
                      <p className="text-xs font-semibold text-[#C2410C] mb-2">✅ 바로 해볼 액션</p>
                      <ul className="space-y-1">
                        {aiReport.actions.map((a, i) => (
                          <li key={i} className="text-xs text-[#111827] flex gap-1.5"><span className="text-[#C2410C]">{i + 1}.</span>{a}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      </div>
    </PageShell>
  );
}
