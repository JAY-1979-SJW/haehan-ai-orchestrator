"use client";
/** KeywordsClient — 블로그 검색 / 경쟁사 조사(쇼핑) / 키워드 도구 / 시장 분석 탭 */
import { useState } from "react";
import {
  runNaverBlogSearch,
  runNaverShoppingSearch,
  getNaverBlogSearchResults,
  getShoppingHistory,
  crawlNaverShopping,
  getCrawlReport,
  getShoppingKeywordSummary,
  getShoppingMallAnalysis,
  getShoppingPriceDist,
  type ShoppingHistoryResponse,
  type CrawlResult,
  type KeywordSummaryResponse,
  type MallAnalysisResponse,
  type PriceDistResponse,
} from "@/lib/assistant/api";
import { BlogTab } from "./components/BlogTab";
import { ShoppingTab } from "./components/ShoppingTab";
import { ToolsTab } from "./components/ToolsTab";
import { AnalysisTab } from "./components/AnalysisTab";
import type { SearchState } from "./components/types";

type Tab = "blog" | "shopping" | "tools" | "analysis";

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

  // 시장 분석 상태
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [kwSummary, setKwSummary] = useState<KeywordSummaryResponse | null>(null);
  const [mallData, setMallData] = useState<MallAnalysisResponse | null>(null);
  const [priceDist, setPriceDist] = useState<PriceDistResponse | null>(null);
  const [excludeLarge, setExcludeLarge] = useState(false);

  const TABS: { id: Tab; label: string }[] = [
    { id: "blog",     label: "블로그 검색" },
    { id: "shopping", label: "경쟁사 조사" },
    { id: "tools",    label: "키워드 도구" },
    { id: "analysis", label: "시장 분석" },
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

  const handleFullAnalysis = async () => {
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const [ks, ma, pd] = await Promise.all([
        getShoppingKeywordSummary(),
        getShoppingMallAnalysis(undefined, 30),
        getShoppingPriceDist(),
      ]);
      setKwSummary(ks);
      setMallData(ma);
      setPriceDist(pd);
    } catch (e) {
      setAnalysisError(String(e));
    } finally {
      setAnalysisLoading(false);
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

        {tab === "blog" && (
          <BlogTab
            blogQuery={blogQuery}
            setBlogQuery={setBlogQuery}
            blogPages={blogPages}
            setBlogPages={setBlogPages}
            blogState={blogState}
            onRun={handleBlogRun}
            onList={handleBlogList}
          />
        )}

        {tab === "shopping" && (
          <ShoppingTab
            shopQuery={shopQuery}
            setShopQuery={setShopQuery}
            shopPages={shopPages}
            setShopPages={setShopPages}
            shopState={shopState}
            historyData={historyData}
            historyLoading={historyLoading}
            historyError={historyError}
            crawlResult={crawlResult}
            crawlLoading={crawlLoading}
            crawlError={crawlError}
            crawlReport={crawlReport}
            crawlReportLoading={crawlReportLoading}
            crawlReportError={crawlReportError}
            onShopRun={handleShopRun}
            onShopHistory={handleShopHistory}
            onCrawl={handleCrawl}
            onCrawlReport={handleCrawlReport}
          />
        )}

        {tab === "tools" && <ToolsTab />}

        {tab === "analysis" && (
          <AnalysisTab
            analysisLoading={analysisLoading}
            analysisError={analysisError}
            kwSummary={kwSummary}
            mallData={mallData}
            priceDist={priceDist}
            excludeLarge={excludeLarge}
            setExcludeLarge={setExcludeLarge}
            onFullAnalysis={handleFullAnalysis}
          />
        )}
      </div>
    </div>
  );
}
