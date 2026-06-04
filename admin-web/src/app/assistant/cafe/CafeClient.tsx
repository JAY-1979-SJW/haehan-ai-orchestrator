"use client";
/** /assistant/cafe — 네이버 카페 수집·분석 조회 (read-only) */
import { useState, useCallback, useEffect } from "react";
import { PageShell } from "@/components/ui/PageShell";
import {
  getCafeSummary, getMyCafes, getCafeArticles, getCafeKB,
  type MyCafe, type CafeArticle, type CafeSummary, type CafeKB, type CafeCategorySummary,
} from "@/lib/assistant/api";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";

type Tab = "summary" | "my-cafes" | "articles" | "report";

const CATEGORIES = ["노무","계약·하도급","공사관리","세무·회계","법규·인허가","안전","행정·서류","장비·자재","커뮤니티","기타"];

const CAT_COLOR: Record<string, string> = {
  "노무": "bg-blue-50 text-blue-700 border-blue-200",
  "세무·회계": "bg-green-50 text-green-700 border-green-200",
  "계약·하도급": "bg-purple-50 text-purple-700 border-purple-200",
  "공사관리": "bg-orange-50 text-orange-700 border-orange-200",
  "법규·인허가": "bg-red-50 text-red-700 border-red-200",
  "안전": "bg-yellow-50 text-yellow-700 border-yellow-200",
  "행정·서류": "bg-indigo-50 text-indigo-700 border-indigo-200",
  "장비·자재": "bg-teal-50 text-teal-700 border-teal-200",
  "커뮤니티": "bg-pink-50 text-pink-700 border-pink-200",
  "기타": "bg-gray-50 text-gray-600 border-gray-200",
};

function CategoryCard({ s }: { s: CafeCategorySummary }) {
  const [open, setOpen] = useState(false);
  const color = CAT_COLOR[s.category] ?? CAT_COLOR["기타"];

  return (
    <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
      {/* 헤더 */}
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
          {/* 키워드 */}
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

          {/* 상위 질문 */}
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

          {/* 반복 질문 군집 */}
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
  const [artCategory, setArtCategory] = useState("");
  const [artLoading, setArtLoading] = useState(false);
  const [artError, setArtError] = useState<string | null>(null);
  const [artSource, setArtSource] = useState("");

  const [kb, setKb] = useState<CafeKB | null>(null);
  const [kbLoading, setKbLoading] = useState(false);
  const [kbError, setKbError] = useState<string | null>(null);

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

  const apiPost = async (path: string, body: unknown) => {
    const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
    const r = await fetch(`/api/proxy${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
      body: JSON.stringify(body),
    });
    return r.json();
  };

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
      const d = await apiPost("/api/v1/naver-cafe/collect", { cafe_url: url, days: 90 });
      if (d.ok) { setCollectMsg(`${cafe.cafe_name || cafe.cafe_id} — 게시글 ${d.collected}건 수집 완료`); loadSummary(); }
      else setCollectMsg(`수집 실패: ${d.detail || d.error || ""}`);
    } catch (e) { setCollectMsg(`수집 실패: ${e instanceof Error ? e.message : ""}`); }
    finally { setCollectingUrl(null); }
  };

  const loadArticles = useCallback(async (offset = 0, category = artCategory) => {
    setArtLoading(true); setArtError(null);
    try {
      const r = await getCafeArticles(50, offset, category || undefined);
      setArticles(r.items); setArtTotal(r.total); setArtOffset(offset); setArtSource(r.source_file);
    }
    catch (e: unknown) { setArtError(e instanceof Error ? e.message : String(e)); }
    finally { setArtLoading(false); }
  }, [artCategory]);

  const loadKB = useCallback(async () => {
    setKbLoading(true); setKbError(null);
    try { setKb(await getCafeKB()); }
    catch (e: unknown) { setKbError(e instanceof Error ? e.message : String(e)); }
    finally { setKbLoading(false); }
  }, []);

  useEffect(() => {
    if (tab === "summary" && !summary) loadSummary();
    if (tab === "my-cafes" && cafes.length === 0) loadCafes();
    if (tab === "articles" && articles.length === 0) loadArticles(0);
    if (tab === "report" && !kb) loadKB();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const TABS: { id: Tab; label: string }[] = [
    { id: "summary",  label: "수집 현황" },
    { id: "my-cafes", label: "내 카페 목록" },
    { id: "articles", label: "수집 게시글" },
    { id: "report",   label: "분석 보고서" },
  ];

  const confidenceBadge = (c: string) => ({
    high:   "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
    medium: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
    low:    "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
  }[c] ?? "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]");

  return (
    <PageShell title="카페 탐색" description="네이버 카페 수집 · 분석" chatDomain="naver">
      <div className="space-y-4">
      <ReadOnlyModeBanner />
      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">네이버 카페</span>
          <span className="text-xs bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] px-2 py-0.5 rounded font-semibold">조회 전용</span>
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
            </div>
            <p className="text-[11px] text-[#9CA3AF]">[내 카페 수집]으로 가입 카페를 가져온 뒤, 각 카페의 [게시글 수집]을 누르세요. (네이버 로그인 필요)</p>
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
              <select value={artCategory}
                onChange={(e) => { setArtCategory(e.target.value); loadArticles(0, e.target.value); }}
                className="border border-[#E5E7EB] rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D4ED8]">
                <option value="">전체 카테고리</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
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
                    {["카테고리","유형","제목","날짜","조회","신뢰도"].map((h) => (
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

        {/* ── 분석 보고서 ── */}
        {tab === "report" && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <button onClick={loadKB} disabled={kbLoading}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
                {kbLoading ? "불러오는 중…" : "새로고침"}
              </button>
              {kb && (
                <div className="flex gap-3 text-xs text-[#6B7280]">
                  <span>총 <b className="text-[#111827]">{kb.total.toLocaleString()}</b>건 분석</span>
                  <span>카테고리 <b className="text-[#111827]">{kb.categories.length}</b>개</span>
                  <span className="text-[#9CA3AF]">{kb.source_file}</span>
                </div>
              )}
            </div>
            {kbError && <p className="text-xs text-[#DC2626]">오류: {kbError}</p>}

            {kb && (
              <>
                {/* 전체 요약 카드 */}
                <div className="grid grid-cols-4 gap-3">
                  {kb.categories.map((s) => (
                    <div key={s.category} className={`rounded-lg p-3 border ${CAT_COLOR[s.category] ?? CAT_COLOR["기타"]}`}>
                      <p className="text-xs font-semibold">{s.category}</p>
                      <p className="text-lg font-bold">{s.total.toLocaleString()}<span className="text-xs font-normal ml-1">건</span></p>
                      <p className="text-xs opacity-75">질문 {s.question_count.toLocaleString()}건 · 조회 {s.total_views.toLocaleString()}</p>
                    </div>
                  ))}
                </div>

                {/* 카테고리별 상세 아코디언 */}
                <div className="space-y-2">
                  {kb.categories.map((s) => (
                    <CategoryCard key={s.category} s={s} />
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
      </div>
    </PageShell>
  );
}
