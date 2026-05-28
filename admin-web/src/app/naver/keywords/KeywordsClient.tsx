"use client";
/** KeywordsClient — 블로그 검색 / 경쟁사 조사(쇼핑) / 키워드 도구 탭 */
import { useState } from "react";
import {
  runNaverBlogSearch,
  runNaverShoppingSearch,
  getNaverBlogSearchResults,
  getShoppingHistory,
  crawlNaverShopping,
  getCrawlReport,
  type SearchRunResult,
  type ShoppingHistoryResponse,
  type ShoppingHistoryItem,
  type CrawlResult,
} from "@/lib/assistant/api";

type Tab = "blog" | "shopping" | "tools";

const KEYWORD_TOOLS = [
  {
    key: "datalab",
    label: "네이버 데이터랩",
    description: "검색어 트렌드, 쇼핑 카테고리 트렌드, 지역별·연령별 통계 제공.",
    href: "https://datalab.naver.com/",
  },
  {
    key: "shopping_insight",
    label: "쇼핑인사이트",
    description: "쇼핑 카테고리별 클릭 추이, 기기별·성별·연령별 분석 제공.",
    href: "https://datalab.naver.com/shoppingInsight/sCategory.naver",
  },
  {
    key: "search_ad",
    label: "검색광고 키워드 도구",
    description: "키워드별 검색 수, 클릭 수, 경쟁 강도 조회. 네이버 광고 계정 필요.",
    href: "https://searchad.naver.com/",
  },
];

interface SearchState {
  running: boolean;
  result: SearchRunResult | null;
  error: string | null;
  listData: unknown[] | null;
  listLoading: boolean;
  listError: string | null;
}

const initState = (): SearchState => ({
  running: false,
  result: null,
  error: null,
  listData: null,
  listLoading: false,
  listError: null,
});

export default function KeywordsClient() {
  const [tab, setTab] = useState<Tab>("blog");

  const [blogQuery, setBlogQuery] = useState("");
  const [blogPages, setBlogPages] = useState(1);
  const [blogState, setBlogState] = useState<SearchState>(initState());

  const [shopQuery, setShopQuery] = useState("");
  const [shopPages, setShopPages] = useState(1);
  const [shopState, setShopState] = useState<SearchState>(initState());

  // 경쟁사 분석 이력 상태
  const [historyData, setHistoryData] = useState<ShoppingHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // CDP 크롤링 상태
  const [crawlResult, setCrawlResult] = useState<CrawlResult | null>(null);
  const [crawlLoading, setCrawlLoading] = useState(false);
  const [crawlError, setCrawlError] = useState<string | null>(null);
  const [crawlReport, setCrawlReport] = useState<CrawlResult | null>(null);
  const [crawlReportLoading, setCrawlReportLoading] = useState(false);
  const [crawlReportError, setCrawlReportError] = useState<string | null>(null);

  const TABS: { id: Tab; label: string }[] = [
    { id: "blog",     label: "블로그 검색" },
    { id: "shopping", label: "경쟁사 조사" },
    { id: "tools",    label: "키워드 도구" },
  ];

  const handleBlogRun = async () => {
    if (!blogQuery.trim()) return;
    setBlogState((s) => ({ ...s, running: true, result: null, error: null }));
    try {
      const result = await runNaverBlogSearch(blogQuery.trim(), blogPages);
      setBlogState((s) => ({ ...s, running: false, result }));
    } catch (e) {
      setBlogState((s) => ({ ...s, running: false, error: String(e) }));
    }
  };

  const handleBlogList = async () => {
    setBlogState((s) => ({ ...s, listLoading: true, listData: null, listError: null }));
    try {
      const data = await getNaverBlogSearchResults(blogQuery.trim() || undefined, 30);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setBlogState((s) => ({ ...s, listLoading: false, listData: (data as any)?.items ?? data }));
    } catch (e) {
      setBlogState((s) => ({ ...s, listLoading: false, listError: String(e) }));
    }
  };

  const handleShopRun = async () => {
    if (!shopQuery.trim()) return;
    setShopState((s) => ({ ...s, running: true, result: null, error: null }));
    try {
      const result = await runNaverShoppingSearch(shopQuery.trim(), shopPages);
      setShopState((s) => ({ ...s, running: false, result }));
    } catch (e) {
      setShopState((s) => ({ ...s, running: false, error: String(e) }));
    }
  };

  const handleCrawl = async () => {
    if (!shopQuery.trim()) return;
    setCrawlLoading(true);
    setCrawlResult(null);
    setCrawlError(null);
    try {
      const data = await crawlNaverShopping(shopQuery.trim(), 40);
      setCrawlResult(data);
    } catch (e) {
      setCrawlError(String(e));
    } finally {
      setCrawlLoading(false);
    }
  };

  const handleCrawlReport = async () => {
    if (!shopQuery.trim()) return;
    setCrawlReportLoading(true);
    setCrawlReport(null);
    setCrawlReportError(null);
    try {
      const data = await getCrawlReport(shopQuery.trim());
      setCrawlReport(data);
    } catch (e) {
      setCrawlReportError(String(e));
    } finally {
      setCrawlReportLoading(false);
    }
  };

  const handleShopHistory = async () => {
    setHistoryLoading(true);
    setHistoryData(null);
    setHistoryError(null);
    try {
      const data = await getShoppingHistory(shopQuery.trim() || undefined, 100);
      setHistoryData(data);
    } catch (e) {
      setHistoryError(String(e));
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">네이버 키워드 · 경쟁사 조사</span>
        </div>

        {/* 탭 헤더 */}
        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id
                  ? "border-[#F97316] text-[#F97316] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 블로그 검색 ── */}
        {tab === "blog" && (
          <div className="space-y-4 max-w-2xl">
            <div className="flex gap-2">
              <input
                type="text"
                value={blogQuery}
                onChange={(e) => setBlogQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleBlogRun()}
                placeholder="블로그 검색어를 입력하세요"
                className="flex-1 border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827] placeholder-[#9CA3AF]"
              />
              <select
                value={blogPages}
                onChange={(e) => setBlogPages(Number(e.target.value))}
                className="border border-[#E5E7EB] rounded-lg px-2 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827]"
              >
                {[1, 2, 3, 5].map((n) => (
                  <option key={n} value={n}>{n}페이지</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleBlogRun}
                disabled={blogState.running || !blogQuery.trim()}
                className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA6C0A] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {blogState.running ? "실행 중…" : "검색 실행"}
              </button>
              <button
                onClick={handleBlogList}
                disabled={blogState.listLoading}
                className="px-4 py-2 border border-[#E5E7EB] text-[#374151] text-sm font-semibold rounded-lg hover:bg-[#F9FAFB] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {blogState.listLoading ? "조회 중…" : "결과 조회"}
              </button>
            </div>

            {blogState.error && (
              <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#DC2626] mb-1">오류</p>
                <p className="text-xs text-[#7F1D1D] font-mono">{blogState.error}</p>
              </div>
            )}

            {blogState.result && (
              <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#16A34A] mb-2">실행 완료</p>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <dt className="text-[#6B7280]">상태</dt>
                  <dd className="font-mono text-[#111827]">{blogState.result.status}</dd>
                  <dt className="text-[#6B7280]">수집 건수</dt>
                  <dd className="font-mono text-[#111827]">{blogState.result.collected}</dd>
                  <dt className="text-[#6B7280]">DB 상태</dt>
                  <dd className="font-mono text-[#111827]">{blogState.result.db_status}</dd>
                  <dt className="text-[#6B7280]">소요 시간</dt>
                  <dd className="font-mono text-[#111827]">{blogState.result.duration_ms} ms</dd>
                </dl>
              </div>
            )}

            {blogState.listError && (
              <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#DC2626] mb-1">결과 조회 오류</p>
                <p className="text-xs text-[#7F1D1D] font-mono">{blogState.listError}</p>
              </div>
            )}

            {blogState.listData && (
              <div className="border border-[#E5E7EB] bg-white rounded-xl p-4">
                <p className="text-xs font-semibold text-[#374151] mb-2">
                  결과 목록 ({Array.isArray(blogState.listData) ? blogState.listData.length : "—"}건)
                </p>
                <pre className="text-xs text-[#374151] font-mono whitespace-pre-wrap overflow-x-auto max-h-64">
                  {JSON.stringify(blogState.listData, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* ── 경쟁사 조사 ── */}
        {tab === "shopping" && (
          <div className="space-y-4 max-w-3xl">
            <div className="border border-[#BFDBFE] bg-[#EFF6FF] rounded-xl px-4 py-3">
              <p className="text-xs font-bold text-[#1D4ED8]">타업체 경쟁사 조사 모드</p>
              <p className="text-xs text-[#1E40AF] mt-0.5">
                네이버 쇼핑에서 경쟁 상품·브랜드·가격대를 수집합니다. 수집된 데이터는 DB에 저장되어 비교 분석에 활용됩니다.
              </p>
            </div>

            {/* 검색어 입력 */}
            <div className="flex gap-2">
              <input
                type="text"
                value={shopQuery}
                onChange={(e) => setShopQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleShopRun()}
                placeholder="경쟁 상품·브랜드명 입력 (예: LED 무드등, 인테리어 조명)"
                className="flex-1 border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827] placeholder-[#9CA3AF]"
              />
              <select
                value={shopPages}
                onChange={(e) => setShopPages(Number(e.target.value))}
                className="border border-[#E5E7EB] rounded-lg px-2 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827]"
              >
                {[1, 2, 3, 5].map((n) => (
                  <option key={n} value={n}>{n}페이지</option>
                ))}
              </select>
            </div>

            {/* 버튼 행 */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleShopRun}
                disabled={shopState.running || !shopQuery.trim()}
                className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA6C0A] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {shopState.running ? "수집 중…" : "경쟁사 수집"}
              </button>
              <button
                onClick={handleShopHistory}
                disabled={historyLoading}
                className="px-4 py-2 border border-[#6366F1] text-[#6366F1] text-sm font-semibold rounded-lg hover:bg-[#EEF2FF] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {historyLoading ? "분석 중…" : "분석 조회"}
              </button>
              <button
                onClick={handleCrawl}
                disabled={crawlLoading || !shopQuery.trim()}
                className="px-4 py-2 bg-[#1D4ED8] text-white text-sm font-semibold rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {crawlLoading ? "크롤링 중…" : "리뷰·별점 수집 (CDP)"}
              </button>
              <button
                onClick={handleCrawlReport}
                disabled={crawlReportLoading || !shopQuery.trim()}
                className="px-4 py-2 border border-[#1D4ED8] text-[#1D4ED8] text-sm font-semibold rounded-lg hover:bg-[#EFF6FF] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {crawlReportLoading ? "조회 중…" : "크롤링 결과 보기"}
              </button>
            </div>

            {/* CDP 크롤링 오류 */}
            {crawlError && (
              <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#DC2626] mb-1">CDP 크롤링 오류</p>
                <p className="text-xs text-[#7F1D1D] font-mono">{crawlError}</p>
              </div>
            )}

            {/* CDP 크롤링 결과 */}
            {crawlResult && (
              <div className="space-y-3">
                <div className={`border rounded-xl p-4 ${crawlResult.ok ? "border-[#BFDBFE] bg-[#EFF6FF]" : "border-[#FCA5A5] bg-[#FEF2F2]"}`}>
                  <p className={`text-xs font-semibold mb-2 ${crawlResult.ok ? "text-[#1D4ED8]" : "text-[#DC2626]"}`}>
                    CDP 크롤링 {crawlResult.ok ? "완료" : "실패"} — {crawlResult.count ?? 0}건 수집 ({crawlResult.duration_ms} ms)
                  </p>
                  {crawlResult.stats && (
                    <div className="grid grid-cols-3 gap-3 text-xs">
                      <div className="bg-white rounded-lg p-3 border border-[#BFDBFE]">
                        <p className="font-semibold text-[#1D4ED8] mb-1">가격</p>
                        <p className="text-[#374151]">최저 {crawlResult.stats.price.min.toLocaleString()}원</p>
                        <p className="text-[#374151]">평균 {crawlResult.stats.price.avg.toLocaleString()}원</p>
                        <p className="text-[#374151]">최고 {crawlResult.stats.price.max.toLocaleString()}원</p>
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-[#BFDBFE]">
                        <p className="font-semibold text-[#1D4ED8] mb-1">리뷰</p>
                        <p className="text-[#374151]">최소 {crawlResult.stats.review.min}</p>
                        <p className="text-[#374151]">평균 {crawlResult.stats.review.avg}</p>
                        <p className="text-[#374151]">합계 {crawlResult.stats.review.total.toLocaleString()}</p>
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-[#BFDBFE]">
                        <p className="font-semibold text-[#1D4ED8] mb-1">별점</p>
                        <p className="text-[#374151]">평균 {crawlResult.stats.rating.avg}</p>
                        <p className="text-[#374151]">최고 {crawlResult.stats.rating.max}</p>
                      </div>
                    </div>
                  )}
                  {crawlResult.error && (
                    <p className="text-xs text-[#7F1D1D] font-mono mt-1">{crawlResult.error}</p>
                  )}
                </div>

                {crawlResult.products && crawlResult.products.length > 0 && (
                  <div className="border border-[#BFDBFE] rounded-xl overflow-hidden">
                    <p className="text-xs font-semibold text-[#1D4ED8] px-4 py-3 border-b border-[#BFDBFE] bg-[#EFF6FF]">
                      CDP 수집 상품 ({crawlResult.products.length}건)
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-[#DBEAFE] text-[#1E40AF]">
                            <th className="text-right px-3 py-2 font-semibold">#</th>
                            <th className="text-left px-3 py-2 font-semibold">상품명</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">가격</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">리뷰</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">구매수</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">별점</th>
                            <th className="text-left px-3 py-2 font-semibold">판매몰</th>
                          </tr>
                        </thead>
                        <tbody>
                          {crawlResult.products.map((p, idx) => (
                            <tr key={idx} className={idx % 2 === 0 ? "bg-white" : "bg-[#F0F9FF]"}>
                              <td className="px-3 py-2 text-right text-[#9CA3AF]">{p.rank}</td>
                              <td className="px-3 py-2 text-[#111827] max-w-[200px] truncate" title={p.title}>{p.title}</td>
                              <td className="px-3 py-2 text-right font-mono text-[#111827] whitespace-nowrap">
                                {p.price != null ? p.price.toLocaleString() + "원" : "—"}
                              </td>
                              <td className="px-3 py-2 text-right text-[#374151]">
                                {p.review_count != null ? p.review_count.toLocaleString() : "—"}
                              </td>
                              <td className="px-3 py-2 text-right text-[#374151]">
                                {p.buy_count != null ? p.buy_count.toLocaleString() : "—"}
                              </td>
                              <td className="px-3 py-2 text-right text-[#F59E0B]">
                                {p.rating != null ? p.rating.toFixed(1) : "—"}
                              </td>
                              <td className="px-3 py-2 text-[#374151]">{p.mall || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* CDP 보고서 오류 */}
            {crawlReportError && (
              <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#DC2626] mb-1">CDP 보고서 오류</p>
                <p className="text-xs text-[#7F1D1D] font-mono">{crawlReportError}</p>
              </div>
            )}

            {/* CDP 보고서 결과 */}
            {crawlReport && (
              <div className="space-y-3">
                <div className="border border-[#BFDBFE] bg-[#EFF6FF] rounded-xl p-4">
                  <p className="text-xs font-semibold text-[#1D4ED8] mb-2">
                    CDP 보고서 — {crawlReport.keyword} ({crawlReport.count ?? 0}건, {crawlReport.duration_ms} ms)
                  </p>
                  {crawlReport.stats && (
                    <div className="grid grid-cols-3 gap-3 text-xs">
                      <div className="bg-white rounded-lg p-3 border border-[#BFDBFE]">
                        <p className="font-semibold text-[#1D4ED8] mb-1">가격</p>
                        <p className="text-[#374151]">최저 {crawlReport.stats.price.min.toLocaleString()}원</p>
                        <p className="text-[#374151]">평균 {crawlReport.stats.price.avg.toLocaleString()}원</p>
                        <p className="text-[#374151]">최고 {crawlReport.stats.price.max.toLocaleString()}원</p>
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-[#BFDBFE]">
                        <p className="font-semibold text-[#1D4ED8] mb-1">리뷰</p>
                        <p className="text-[#374151]">최소 {crawlReport.stats.review.min}</p>
                        <p className="text-[#374151]">평균 {crawlReport.stats.review.avg}</p>
                        <p className="text-[#374151]">합계 {crawlReport.stats.review.total.toLocaleString()}</p>
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-[#BFDBFE]">
                        <p className="font-semibold text-[#1D4ED8] mb-1">별점</p>
                        <p className="text-[#374151]">평균 {crawlReport.stats.rating.avg}</p>
                        <p className="text-[#374151]">최고 {crawlReport.stats.rating.max}</p>
                      </div>
                    </div>
                  )}
                  {crawlReport.error && (
                    <p className="text-xs text-[#7F1D1D] font-mono mt-1">{crawlReport.error}</p>
                  )}
                </div>

                {crawlReport.products && crawlReport.products.length > 0 && (
                  <div className="border border-[#BFDBFE] rounded-xl overflow-hidden">
                    <p className="text-xs font-semibold text-[#1D4ED8] px-4 py-3 border-b border-[#BFDBFE] bg-[#EFF6FF]">
                      CDP 보고서 상품 ({crawlReport.products.length}건)
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-[#DBEAFE] text-[#1E40AF]">
                            <th className="text-right px-3 py-2 font-semibold">#</th>
                            <th className="text-left px-3 py-2 font-semibold">상품명</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">가격</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">리뷰</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">구매수</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">별점</th>
                            <th className="text-left px-3 py-2 font-semibold">판매몰</th>
                          </tr>
                        </thead>
                        <tbody>
                          {crawlReport.products.map((p, idx) => (
                            <tr key={idx} className={idx % 2 === 0 ? "bg-white" : "bg-[#F0F9FF]"}>
                              <td className="px-3 py-2 text-right text-[#9CA3AF]">{p.rank}</td>
                              <td className="px-3 py-2 text-[#111827] max-w-[200px] truncate" title={p.title}>{p.title}</td>
                              <td className="px-3 py-2 text-right font-mono text-[#111827] whitespace-nowrap">
                                {p.price != null ? p.price.toLocaleString() + "원" : "—"}
                              </td>
                              <td className="px-3 py-2 text-right text-[#374151]">
                                {p.review_count != null ? p.review_count.toLocaleString() : "—"}
                              </td>
                              <td className="px-3 py-2 text-right text-[#374151]">
                                {p.buy_count != null ? p.buy_count.toLocaleString() : "—"}
                              </td>
                              <td className="px-3 py-2 text-right text-[#F59E0B]">
                                {p.rating != null ? p.rating.toFixed(1) : "—"}
                              </td>
                              <td className="px-3 py-2 text-[#374151]">{p.mall || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 수집 오류 */}
            {shopState.error && (
              <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#DC2626] mb-1">오류</p>
                <p className="text-xs text-[#7F1D1D] font-mono">{shopState.error}</p>
              </div>
            )}

            {/* 수집 완료 결과 */}
            {shopState.result && (
              <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#16A34A] mb-2">수집 완료</p>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <dt className="text-[#6B7280]">상태</dt>
                  <dd className="font-mono text-[#111827]">{shopState.result.status}</dd>
                  <dt className="text-[#6B7280]">수집 건수</dt>
                  <dd className="font-mono text-[#111827]">{shopState.result.collected}</dd>
                  <dt className="text-[#6B7280]">DB 상태</dt>
                  <dd className="font-mono text-[#111827]">{shopState.result.db_status}</dd>
                  <dt className="text-[#6B7280]">소요 시간</dt>
                  <dd className="font-mono text-[#111827]">{shopState.result.duration_ms} ms</dd>
                </dl>
              </div>
            )}

            {/* 분석 오류 */}
            {historyError && (
              <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#DC2626] mb-1">분석 조회 오류</p>
                <p className="text-xs text-[#7F1D1D] font-mono">{historyError}</p>
              </div>
            )}

            {/* 분석 결과 */}
            {historyData && (
              <div className="space-y-4">
                {/* 구분선 */}
                <div className="border-t border-[#E5E7EB] pt-4">
                  <p className="text-sm font-bold text-[#111827] mb-3">
                    수집 이력 분석 — 총 {historyData.total}건 ({historyData.duration_ms} ms)
                  </p>
                </div>

                {/* 키워드별 가격 요약 카드 */}
                {Object.keys(historyData.summary).length === 0 ? (
                  <div className="border border-[#E5E7EB] bg-[#F9FAFB] rounded-xl p-6 text-center">
                    <p className="text-sm text-[#6B7280]">수집 이력이 없습니다.</p>
                    <p className="text-xs text-[#9CA3AF] mt-1">먼저 경쟁사 수집을 실행하세요.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {Object.entries(historyData.summary).map(([kw, stat]) => (
                      <div key={kw} className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-2">
                        <p className="text-sm font-bold text-[#111827] truncate">{kw}</p>
                        <p className="text-xs text-[#6B7280]">수집 {stat.count}건</p>
                        <div className="flex gap-3 text-xs font-semibold">
                          <span className="text-[#16A34A]">
                            최저 {stat.min_price != null ? stat.min_price.toLocaleString() + "원" : "—"}
                          </span>
                          <span className="text-[#EA580C]">
                            평균 {stat.avg_price != null ? stat.avg_price.toLocaleString() + "원" : "—"}
                          </span>
                          <span className="text-[#DC2626]">
                            최고 {stat.max_price != null ? stat.max_price.toLocaleString() + "원" : "—"}
                          </span>
                        </div>
                        {stat.brands.length > 0 && (
                          <p className="text-xs text-[#6B7280]">
                            <span className="font-semibold text-[#374151]">브랜드: </span>
                            {stat.brands.join(", ")}
                          </p>
                        )}
                        {stat.mall_names.length > 0 && (
                          <p className="text-xs text-[#6B7280]">
                            <span className="font-semibold text-[#374151]">판매몰: </span>
                            {stat.mall_names.join(", ")}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* 상품 목록 테이블 */}
                {historyData.items.length > 0 && (
                  <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
                    <p className="text-xs font-semibold text-[#374151] px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
                      상품 목록 ({historyData.items.length}건)
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-[#F3F4F6] text-[#6B7280]">
                            <th className="text-left px-3 py-2 font-semibold">상품명</th>
                            <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">최저가</th>
                            <th className="text-left px-3 py-2 font-semibold">브랜드</th>
                            <th className="text-left px-3 py-2 font-semibold">판매몰</th>
                            <th className="text-left px-3 py-2 font-semibold whitespace-nowrap">수집시각</th>
                          </tr>
                        </thead>
                        <tbody>
                          {historyData.items.map((item: ShoppingHistoryItem, idx: number) => (
                            <tr key={idx} className={idx % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"}>
                              <td className="px-3 py-2 text-[#111827] max-w-[200px] truncate">
                                {item.link ? (
                                  <a
                                    href={item.link}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-[#2563EB] hover:underline"
                                    title={item.title}
                                  >
                                    {item.title}
                                  </a>
                                ) : (
                                  <span title={item.title}>{item.title}</span>
                                )}
                              </td>
                              <td className="px-3 py-2 text-right font-mono text-[#111827] whitespace-nowrap">
                                {item.lprice != null ? item.lprice.toLocaleString() + "원" : "—"}
                              </td>
                              <td className="px-3 py-2 text-[#374151]">{item.brand || "—"}</td>
                              <td className="px-3 py-2 text-[#374151]">{item.mall_name || "—"}</td>
                              <td className="px-3 py-2 text-[#9CA3AF] whitespace-nowrap">
                                {item.collected_at ? item.collected_at.slice(0, 16).replace("T", " ") : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── 키워드 도구 ── */}
        {tab === "tools" && (
          <div className="space-y-3">
            <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl px-4 py-3 flex items-start gap-3">
              <span className="text-[#F97316] text-base mt-0.5">!</span>
              <div>
                <p className="text-xs font-bold text-[#C2410C]">외부 도구 이용 안내</p>
                <p className="text-xs text-[#78350F] mt-0.5">
                  아래 도구들은 네이버 외부 사이트로 이동합니다. 네이버 계정 로그인이 필요할 수 있습니다.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {KEYWORD_TOOLS.map((tool) => (
                <div key={tool.key} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex flex-col gap-3">
                  <div>
                    <p className="text-sm font-bold text-[#111827]">{tool.label}</p>
                    <p className="text-xs text-[#6B7280] mt-1">{tool.description}</p>
                  </div>
                  <a
                    href={tool.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-auto inline-block px-4 py-2 bg-[#F97316] text-white text-xs font-semibold rounded-lg hover:bg-[#EA6C0A] transition-colors text-center"
                  >
                    바로가기
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
