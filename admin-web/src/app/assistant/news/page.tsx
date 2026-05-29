"use client";
/** /assistant/news — 네이버 뉴스 조회 (read-only) */
import { useState, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import {
  getNewsMain,
  getNewsSearch,
  getNewsArticle,
  type NewsPressBlock,
  type NewsArticleItem,
  type NewsArticleDetail,
} from "@/lib/assistant/api";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";

type Tab = "main" | "search" | "article";

export default function NewsPage() {
  const [tab, setTab] = useState<Tab>("main");

  // 메인 뉴스
  const [mainBlocks, setMainBlocks] = useState<NewsPressBlock[]>([]);
  const [mainLoading, setMainLoading] = useState(false);
  const [mainError, setMainError] = useState<string | null>(null);
  const [mainLoaded, setMainLoaded] = useState(false);

  // 검색
  const [query, setQuery] = useState("");
  const [searchItems, setSearchItems] = useState<NewsArticleItem[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // 기사 본문
  const [articleUrl, setArticleUrl] = useState("");
  const [article, setArticle] = useState<NewsArticleDetail | null>(null);
  const [articleLoading, setArticleLoading] = useState(false);
  const [articleError, setArticleError] = useState<string | null>(null);

  const loadMain = useCallback(async () => {
    setMainLoading(true);
    setMainError(null);
    try {
      const res = await getNewsMain();
      setMainBlocks(res.blocks);
      setMainLoaded(true);
    } catch (e: unknown) {
      setMainError(e instanceof Error ? e.message : String(e));
    } finally {
      setMainLoading(false);
    }
  }, []);

  const doSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearchLoading(true);
    setSearchError(null);
    try {
      const res = await getNewsSearch(query.trim());
      setSearchItems(res.items);
    } catch (e: unknown) {
      setSearchError(e instanceof Error ? e.message : String(e));
    } finally {
      setSearchLoading(false);
    }
  }, [query]);

  const loadArticle = useCallback(async () => {
    if (!articleUrl.trim()) return;
    setArticleLoading(true);
    setArticleError(null);
    setArticle(null);
    try {
      const res = await getNewsArticle(articleUrl.trim());
      setArticle(res);
    } catch (e: unknown) {
      setArticleError(e instanceof Error ? e.message : String(e));
    } finally {
      setArticleLoading(false);
    }
  }, [articleUrl]);

  const TAB_ITEMS: { id: Tab; label: string }[] = [
    { id: "main",    label: "메인 뉴스" },
    { id: "search",  label: "뉴스 검색" },
    { id: "article", label: "기사 본문" },
  ];

  return (
    <PageShell title="뉴스 수집" description="네이버 뉴스 검색 · 수집" chatDomain="naver">
      <div className="space-y-4">
      <ReadOnlyModeBanner />

      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">네이버 뉴스</span>
          <span className="text-xs bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] px-2 py-0.5 rounded font-semibold">
            조회 전용
          </span>
        </div>

        {/* 탭 */}
        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TAB_ITEMS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id
                  ? "border-[#1D4ED8] text-[#1D4ED8] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 메인 뉴스 탭 */}
        {tab === "main" && (
          <div className="space-y-3">
            {!mainLoaded && (
              <button
                onClick={loadMain}
                disabled={mainLoading}
                className="px-4 py-2 bg-[#1D4ED8] text-white text-sm rounded-lg disabled:opacity-50"
              >
                {mainLoading ? "불러오는 중…" : "메인 뉴스 불러오기"}
              </button>
            )}
            {mainLoaded && (
              <button
                onClick={loadMain}
                disabled={mainLoading}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50"
              >
                {mainLoading ? "새로고침 중…" : "새로고침"}
              </button>
            )}
            {mainError && <p className="text-xs text-[#DC2626]">오류: {mainError}</p>}
            {mainBlocks.map((block, i) => (
              <div key={i} className="border border-[#E5E7EB] rounded-lg p-3">
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-sm font-semibold text-[#111827]">{block.press}</span>
                  {block.updated && (
                    <span className="text-xs text-[#9CA3AF]">{block.updated}</span>
                  )}
                </div>
                <ul className="space-y-1">
                  {block.articles.map((a, j) => (
                    <li key={j}>
                      <a
                        href={a.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-[#1D4ED8] hover:underline line-clamp-1"
                      >
                        {a.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* 뉴스 검색 탭 */}
        {tab === "search" && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
                placeholder="검색어 입력 후 Enter"
                className="flex-1 border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1D4ED8]"
              />
              <button
                onClick={doSearch}
                disabled={searchLoading || !query.trim()}
                className="px-4 py-2 bg-[#1D4ED8] text-white text-sm rounded-lg disabled:opacity-50"
              >
                {searchLoading ? "검색 중…" : "검색"}
              </button>
            </div>
            {searchError && <p className="text-xs text-[#DC2626]">오류: {searchError}</p>}
            <div className="space-y-2">
              {searchItems.map((item, i) => (
                <div key={i} className="border border-[#E5E7EB] rounded-lg p-3">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-[#1D4ED8] hover:underline"
                  >
                    {item.title}
                  </a>
                  <div className="flex gap-2 mt-1">
                    {item.press && (
                      <span className="text-xs text-[#6B7280]">{item.press}</span>
                    )}
                    {item.datetime && (
                      <span className="text-xs text-[#9CA3AF]">{item.datetime}</span>
                    )}
                  </div>
                  {item.summary && (
                    <p className="text-xs text-[#374151] mt-1 line-clamp-2">{item.summary}</p>
                  )}
                  <button
                    onClick={() => { setArticleUrl(item.url); setTab("article"); }}
                    className="mt-1 text-xs text-[#6B7280] hover:text-[#1D4ED8]"
                  >
                    → 본문 보기
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 기사 본문 탭 */}
        {tab === "article" && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={articleUrl}
                onChange={(e) => setArticleUrl(e.target.value)}
                placeholder="https://n.news.naver.com/article/..."
                className="flex-1 border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1D4ED8]"
              />
              <button
                onClick={loadArticle}
                disabled={articleLoading || !articleUrl.trim()}
                className="px-4 py-2 bg-[#1D4ED8] text-white text-sm rounded-lg disabled:opacity-50"
              >
                {articleLoading ? "불러오는 중…" : "불러오기"}
              </button>
            </div>
            {articleError && <p className="text-xs text-[#DC2626]">오류: {articleError}</p>}
            {article && (
              <div className="border border-[#E5E7EB] rounded-lg p-4 space-y-3">
                <h2 className="text-base font-bold text-[#111827]">{article.title}</h2>
                <div className="flex gap-3 text-xs text-[#6B7280]">
                  {article.press && <span>{article.press}</span>}
                  {article.datetime && <span>{article.datetime}</span>}
                </div>
                {article.summary && (
                  <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-lg p-3">
                    <p className="text-xs font-semibold text-[#16A34A] mb-1">요약 (첫 3문장)</p>
                    <p className="text-sm text-[#111827]">{article.summary}</p>
                  </div>
                )}
                <div className="border-t border-[#E5E7EB] pt-3">
                  <p className="text-xs text-[#9CA3AF] mb-1">
                    본문 ({article.body.length}자)
                  </p>
                  <p className="text-sm text-[#374151] leading-relaxed whitespace-pre-line">
                    {article.body}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      </div>
    </PageShell>
  );
}
