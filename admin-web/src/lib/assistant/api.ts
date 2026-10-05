/**
 * 비서앱 MVP read-only API client — APP_UI_SHELL_READONLY_API_WIRING_01
 * 보강: APP_UI_READONLY_BACKEND_STATUS_CARDS_01
 *
 * GET 전용 — POST/PUT/PATCH/DELETE 함수 없음
 * mutation 연결 금지: tasks 실행/approve/reject/execute 없음
 */
import type { ApiConnectionMeta, ErrorKind } from "@/types/assistant";

// 모든 API 호출은 /api/proxy/* 를 통해 서버사이드에서 인증 처리.
// 클라이언트 번들에 자격증명 미포함.
export const API_BASE = "/api/proxy";

// _AUTH_HEADER 제거 완료 — proxy 라우트(src/app/api/proxy/[...path]/route.ts)가 처리
const _AUTH_HEADER = "";

export type ApiState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T; meta: ApiConnectionMeta }
  | { status: "empty"; meta: ApiConnectionMeta }
  | { status: "error"; message: string; meta: ApiConnectionMeta }
  | { status: "mock_fallback"; data: T; meta: ApiConnectionMeta };

export function makeMeta(
  source: ApiConnectionMeta["source"],
  error_kind: ErrorKind = null,
): ApiConnectionMeta {
  return {
    source,
    last_checked: new Date().toISOString(),
    error_kind,
    is_read_only: true,
    mutation_allowed: false,
  };
}

export interface HealthResponse {
  status: string;
  service?: string;
  version?: string;
  dry_run_gate_enabled?: boolean;
}

export interface InboxItem {
  id?: string;
  item_id?: string;
  subject?: string;
  title?: string;
  from?: string;
  sender?: string;
  source_account?: string;
  source_type?: string;
  received_at?: string;
  category?: string;
  read?: boolean;
  status?: string;
  body_raw?: string;
  body_summary?: string;
  linked_task_id?: string;
  external_id?: string;
  metadata?: Record<string, unknown>;
}

export interface InboxResponse {
  items: InboxItem[];
  total: number;
}

async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_AUTH_HEADER) headers["Authorization"] = _AUTH_HEADER;
  const res = await fetch(`${API_BASE}${path}`, { method: "GET", headers, signal });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_AUTH_HEADER) headers["Authorization"] = _AUTH_HEADER;
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers, signal,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

/** GET /api/v1/health */
export async function getAssistantHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  return getJson<HealthResponse>("/api/v1/health", signal);
}

/** GET /api/v1/inbox — 배열 직접 반환, InboxResponse로 정규화 */
export async function getAssistantInbox(
  signal?: AbortSignal,
): Promise<InboxResponse> {
  const raw = await getJson<InboxItem[] | InboxResponse>("/api/v1/inbox", signal);
  if (Array.isArray(raw)) {
    return { items: raw, total: raw.length };
  }
  return raw as InboxResponse;
}

// ── APP_UI_READONLY_STATUS_CARDS_API_BIND_01 ──────────────────────────────

export interface AppHealthSummaryData {
  service: string;
  health_status: string;
  server_head: string | null;
  origin_head: string | null;
  sync_status: string;
  post_tasks_dry_run_enabled: boolean;
  phase1_closeout_status: string;
  container_health_source: string;
  generated_at: string;
}

export interface AppHealthSummaryResponse {
  ok: boolean;
  data: AppHealthSummaryData;
  meta: { source: string; read_only: true; mutation_allowed: false };
}

export interface AppProviderItem {
  provider_id: string;
  display_name: string;
  category: string;
  current_status: string;
  risk_level: string;
  user_present_login_required: boolean;
  desktop_app_required: boolean;
  cookie_storage_allowed: false;
  token_storage_allowed: false;
  approval_gate_required: boolean;
  automation_status: string;
  server_remote_login_allowed: false;
  certificate_login_required?: boolean;
}

export interface AppProvidersResponse {
  ok: boolean;
  data: { providers: AppProviderItem[] };
  meta: { provider_count: number; read_only: true; mutation_allowed: false };
}

export interface AppStoragePath {
  name: string;
  path: string;
  type: string;
}

export interface AppStorageStatusData {
  storage_paths: AppStoragePath[];
  named_volume_status: string;
  app_logs_bind_mount_status: string;
  app_logs_path: string;
  storage_path: string;
  audit_log_policy: string;
  execution_history_policy: string;
  approval_token_policy: string;
  runtime_cache_policy: string;
}

export interface AppStorageStatusResponse {
  ok: boolean;
  data: AppStorageStatusData;
  meta: { read_only: true; mutation_allowed: false };
}

/** GET /api/v1/app/health/summary — APP_UI_READONLY_STATUS_CARDS_API_BIND_01 */
export async function getAppHealthSummary(
  signal?: AbortSignal,
): Promise<AppHealthSummaryResponse> {
  return getJson<AppHealthSummaryResponse>("/api/v1/app/health/summary", signal);
}

/** GET /api/v1/app/providers — APP_UI_READONLY_STATUS_CARDS_API_BIND_01 */
export async function getAppProviders(
  signal?: AbortSignal,
): Promise<AppProvidersResponse> {
  return getJson<AppProvidersResponse>("/api/v1/app/providers", signal);
}

/** GET /api/v1/app/storage/status — APP_UI_READONLY_STATUS_CARDS_API_BIND_01 */
export async function getAppStorageStatus(
  signal?: AbortSignal,
): Promise<AppStorageStatusResponse> {
  return getJson<AppStorageStatusResponse>("/api/v1/app/storage/status", signal);
}

export interface AppLiveSummaryData {
  service: string;
  health_status: string;
  post_tasks_dry_run_enabled: boolean;
  phase1_closeout_status: string;
  container_health_source: string;
  read_only: boolean;
  mutation_allowed: boolean;
  storage: {
    named_volume_status: string;
    app_logs_bind_mount_status: string;
    audit_log_policy: string;
  };
  generated_at: string;
}

export interface AppLiveSummaryResponse {
  ok: boolean;
  data: AppLiveSummaryData;
  meta: { read_only: true; mutation_allowed: false };
}

/** GET /api/v1/app/live-summary — 실시간 운영 요약 (read-only) */
export async function getAppLiveSummary(
  signal?: AbortSignal,
): Promise<AppLiveSummaryResponse> {
  return getJson<AppLiveSummaryResponse>("/api/v1/app/live-summary", signal);
}

export interface AppDeploymentStatusResponse {
  ok: boolean;
  data: {
    server_head: string | null;
    origin_head: string | null;
    state: string;
    build_required: boolean;
    sop_steps: string[];
    deploy_action_allowed: boolean;
    generated_at: string;
  };
  meta: { read_only: true; mutation_allowed: false };
}

/** GET /api/v1/app/deployment-status — 배포 상태 (read-only, 실행 없음) */
export async function getAppDeploymentStatus(
  signal?: AbortSignal,
): Promise<AppDeploymentStatusResponse> {
  return getJson<AppDeploymentStatusResponse>("/api/v1/app/deployment-status", signal);
}

// ── APP_LOGS_AUDIT_READONLY_VIEW_01 ───────────────────────────────────────

export type { OpsAuditEventsResponse, OpsSummaryResponse } from "@/types/assistant";

/** GET /api/v1/ops/audit-events — read-only 감사 이벤트 */
export async function getOpsAuditEvents(signal?: AbortSignal) {
  const { events } = await getJson<{ events: unknown[] }>("/api/v1/ops/audit-events", signal);
  return { events } as import("@/types/assistant").OpsAuditEventsResponse;
}

/** GET /api/v1/ops/summary — read-only 운영 요약 */
export async function getOpsSummary(signal?: AbortSignal) {
  return getJson<import("@/types/assistant").OpsSummaryResponse>("/api/v1/ops/summary", signal);
}

export interface OpsApprovalItem {
  approvalId?: string;
  taskKey?: string;
  provider?: string;
  riskLevel?: string;
  state?: string;
  requestedAt?: string;
  [k: string]: unknown;
}

export interface OpsApprovalsResponse {
  items: OpsApprovalItem[];
  source: string;
}

/** GET /api/v1/ops/approvals — read-only 승인 대기 큐 (실행/승인 액션 없음) */
export async function getOpsApprovals(signal?: AbortSignal): Promise<OpsApprovalsResponse> {
  return getJson<OpsApprovalsResponse>("/api/v1/ops/approvals", signal);
}

// ── 네이버 뉴스 스크래핑 read-only ───────────────────────────────────────

export interface NewsArticleItem {
  title: string;
  url: string;
  press: string;
  datetime: string;
  summary: string;
}

export interface NewsPressBlock {
  press: string;
  updated: string;
  articles: { title: string; url: string }[];
}

export interface NewsArticleDetail {
  title: string;
  press: string;
  datetime: string;
  summary: string;
  body: string;
  url: string;
  duration_ms?: number;
}

export interface NewsMainResponse {
  blocks: NewsPressBlock[];
  total: number;
  duration_ms: number;
}

export interface NewsSearchResponse {
  items: NewsArticleItem[];
  total: number;
  query: string;
  page: number;
  duration_ms: number;
}

/** GET /api/v1/external/naver/news-main */
export async function getNewsMain(signal?: AbortSignal): Promise<NewsMainResponse> {
  return getJson<NewsMainResponse>("/api/v1/external/naver/news-main", signal);
}

/** GET /api/v1/external/naver/news-search?query=...&page=... */
export async function getNewsSearch(
  query: string,
  page = 1,
  signal?: AbortSignal,
): Promise<NewsSearchResponse> {
  const params = new URLSearchParams({ query, page: String(page) });
  return getJson<NewsSearchResponse>(`/api/v1/external/naver/news-search?${params}`, signal);
}

/** GET /api/v1/external/naver/news-article?url=... */
export async function getNewsArticle(
  url: string,
  signal?: AbortSignal,
): Promise<NewsArticleDetail> {
  const params = new URLSearchParams({ url });
  return getJson<NewsArticleDetail>(`/api/v1/external/naver/news-article?${params}`, signal);
}

// ── 네이버 카페 ──────────────────────────────────────────────────────────────

export interface MyCafe {
  cafe_id: string;
  cafe_name: string;
  href: string;
  member_count: number;
}

export interface CafeArticle {
  article_id: string;
  title: string;
  category: string;
  type: string;
  date: string;
  view_count: string;
  href: string;
  confidence: string;
}

export interface CafeSummary {
  my_cafes_count: number;
  latest_raw_file: string | null;
  latest_raw_count: number;
  latest_classified_file: string | null;
  latest_classified_count: number;
  has_report: boolean;
  latest_report_file: string | null;
  duration_ms: number;
}

export async function getCafeSummary(signal?: AbortSignal): Promise<CafeSummary> {
  return getJson<CafeSummary>("/api/v1/naver-cafe/summary", signal);
}

export async function getMyCafes(signal?: AbortSignal): Promise<{ cafes: MyCafe[]; count: number }> {
  return getJson<{ cafes: MyCafe[]; count: number }>("/api/v1/naver-cafe/my-cafes", signal);
}

/** 가입 카페 변동(신규 가입·탈퇴·이름 변경) — 기준서 docs/specs/2026-10-05_cafe_membership_changes.md */
export interface CafeMember {
  cafe_id: string;
  name: string;
  clubid: string;
}
export interface CafeRename {
  cafe_id: string;
  from: string;
  to: string;
}
export type CafeChangeStatus = "baseline" | "ok" | "blocked" | "needs_confirmation";
export interface CafeChangeResult {
  status: CafeChangeStatus;
  reason: string;
  warning: string;
  baseline: boolean;
  new: CafeMember[];
  left: CafeMember[];
  renamed: CafeRename[];
  total: number;
  previous_total: number;
}
export interface CafeChangeLog {
  at: string;
  new: CafeMember[];
  left: CafeMember[];
  renamed: CafeRename[];
  total: number;
  previous_total: number;
  confirmed_mass_change?: boolean;
}
export interface CafeChangeHistory {
  changes: CafeChangeLog[];
  trend: { at: string; total: number }[];
  summary: { snapshots: number; current_total: number; net_change_since_first: number; joined_in_log: number; left_in_log: number };
}

export async function getMyCafeChanges(limit = 20, signal?: AbortSignal): Promise<CafeChangeHistory> {
  return getJson<CafeChangeHistory>(`/api/v1/naver-cafe/my-cafes/changes?limit=${limit}`, signal);
}

export async function getCafeArticles(
  limit = 50,
  offset = 0,
  category?: string,
  signal?: AbortSignal,
): Promise<{ total: number; items: CafeArticle[]; source_file: string }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (category) params.set("category", category);
  return getJson(`/api/v1/naver-cafe/articles?${params}`, signal);
}

export async function getCafeReport(signal?: AbortSignal): Promise<{ report: string; source_file: string }> {
  return getJson("/api/v1/naver-cafe/report", signal);
}

export interface CafeTopQuestion { title: string; views: string | number; date: string; href: string }
export interface CafeCluster {
  topic: string; size: number; total_views: number; avg_views: number;
  rep_href: string; similar: string[];
}
export interface CafeCategorySummary {
  category: string; total: number; question_count: number; info_count: number;
  notice_count: number; resource_count: number; total_views: number;
  avg_question_views: number;
  top_questions: CafeTopQuestion[];
  top_infos: { title: string; views: string | number; date: string }[];
  keywords: { word: string; count: number }[];
  question_clusters: CafeCluster[];
}
export interface CafeKB {
  generated_at: string; total: number;
  categories: CafeCategorySummary[];
  source_file: string; duration_ms: number;
}

export async function getCafeKB(signal?: AbortSignal): Promise<CafeKB> {
  return getJson<CafeKB>("/api/v1/naver-cafe/kb", signal);
}

// ── 네이버 키워드 검색 ─────────────────────────────────────────
export interface SearchRunResult {
  status: string;
  query: string;
  collected: number;
  db_status: string;
  duration_ms: number;
}

export async function runNaverBlogSearch(query: string, maxPages = 1): Promise<SearchRunResult> {
  const params = new URLSearchParams({ query, max_pages: String(maxPages) });
  return postJson<SearchRunResult>(`/api/v1/external/naver/blog-search/run?${params}`);
}

export async function runNaverShoppingSearch(query: string, maxPages = 1): Promise<SearchRunResult> {
  const params = new URLSearchParams({ query, max_pages: String(maxPages) });
  return postJson<SearchRunResult>(`/api/v1/external/naver/shopping-search/run?${params}`);
}

export async function getNaverSearchStatus(signal?: AbortSignal) {
  return getJson("/api/v1/external/naver/search-status", signal);
}

export async function getNaverBlogSearchResults(query?: string, limit = 30, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query) params.set("query", query);
  return getJson(`/api/v1/external/naver/blog-search?${params}`, signal);
}

export async function getNaverShoppingSearchResults(query?: string, limit = 30, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query) params.set("query", query);
  return getJson(`/api/v1/external/naver/shopping-search?${params}`, signal);
}

export interface ShoppingHistorySummaryItem {
  count: number;
  min_price: number | null;
  max_price: number | null;
  avg_price: number | null;
  brands: string[];
  mall_names: string[];
}

export interface ShoppingHistoryItem {
  query: string;
  title: string;
  link: string;
  lprice: number | null;
  hprice: number | null;
  mall_name: string;
  brand: string;
  maker: string;
  product_id: string;
  collected_at: string;
  source: string;
}

export interface ShoppingHistoryResponse {
  total: number;
  items: ShoppingHistoryItem[];
  limit: number;
  offset: number;
  summary: Record<string, ShoppingHistorySummaryItem>;
  duration_ms: number;
}

export async function getShoppingHistory(
  query?: string,
  limit = 100,
  signal?: AbortSignal,
): Promise<ShoppingHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query) params.set("query", query);
  return getJson<ShoppingHistoryResponse>(
    `/api/v1/external/naver/shopping-search/history?${params}`,
    signal,
  );
}

export interface CrawlResult {
  ok: boolean;
  keyword?: string;
  count?: number;
  products?: Array<{
    rank: number;
    title: string;
    price: number | null;
    mall: string;
    review_count: number | null;
    buy_count: number | null;
    wish_count: number | null;
    rating: number | null;
    delivery: string;
  }>;
  stats?: {
    price: { min: number; avg: number; max: number };
    review: { min: number; avg: number; max: number; total: number };
    rating: { avg: number; max: number };
  };
  duration_ms?: number;
  error?: string;
}

export async function crawlNaverShopping(query: string, limit = 40): Promise<CrawlResult> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return postJson<CrawlResult>(`/api/v1/external/naver/shopping-search/crawl?${params}`);
}

// ── 스마트스토어 ─────────────────────────────────────────────────
export interface SmartStoreStatusResponse {
  catalog: {
    generated_at?: string;
    contract?: Record<string, string>;
    sections?: Array<{
      name: string;
      actions: Array<{ action_id: string; label: string; risk: string; status: string; required_fields?: string[] }>;
      summary: { total: number; implemented: number; approval_gated: number };
    }>;
  };
  db_path: string;
}

export interface SmartStoreHistoryResponse {
  latest: Record<string, unknown>;
  history: Array<Record<string, unknown>>;
  count: number;
}

export async function getSmartStoreStatus(signal?: AbortSignal): Promise<SmartStoreStatusResponse> {
  return getJson<SmartStoreStatusResponse>("/api/v1/smartstore/status", signal);
}

export async function getSmartStoreHistory(signal?: AbortSignal): Promise<SmartStoreHistoryResponse> {
  return getJson<SmartStoreHistoryResponse>("/api/v1/smartstore/submit-history", signal);
}

export async function getSmartStoreFormFields(signal?: AbortSignal) {
  return getJson<{ required: string[]; optional: string[] }>("/api/v1/smartstore/product-form-fields", signal);
}

export async function getCrawlReport(query: string, signal?: AbortSignal): Promise<CrawlResult> {
  const params = new URLSearchParams({ query });
  return getJson<CrawlResult>(`/api/v1/external/naver/shopping-search/crawl-report?${params}`, signal);
}

// ── 쇼핑 시장 분석 API ────────────────────────────────────────────────────

export interface PriceRange {
  label: string;
  lo: number;
  hi: number | null;
  count: number;
}

export interface PriceDistResponse {
  ranges: PriceRange[];
  total_with_price: number;
  keywords: string[];
  duration_ms: number;
}

export interface MallItem {
  mall_name: string;
  count: number;
  min_price: number | null;
  avg_price: number | null;
  max_price: number | null;
  brand_count: number;
  is_large: boolean;
}

export interface MallAnalysisResponse {
  malls: MallItem[];
  total_malls: number;
  specialist_count: number;
  large_malls: MallItem[];
  keywords: string[];
  duration_ms: number;
}

export interface BrandItem {
  brand: string;
  count: number;
  min_price: number | null;
  max_price: number | null;
  mall_count: number;
}

export interface BrandAnalysisResponse {
  brands: BrandItem[];
  total_brands: number;
  keywords: string[];
  duration_ms: number;
}

export interface KeywordSummaryItem {
  query: string;
  count: number;
  min_price: number | null;
  avg_price: number | null;
  max_price: number | null;
  mall_count: number;
  brand_count: number;
}

export interface KeywordSummaryResponse {
  keywords: KeywordSummaryItem[];
  total_products: number;
  duration_ms: number;
}

export interface CompetitionScoreResponse {
  keyword: string;
  score: number;
  detail: {
    product_count: number;
    max_count_in_db: number;
    price_std: number;
    mall_count: number;
    total_mall_count: number;
    n_count: number;
    n_std: number;
    n_malls: number;
  };
  duration_ms: number;
}

/** GET /api/v1/external/naver/shopping-search/analysis/price-dist */
export async function getShoppingPriceDist(
  query?: string,
  signal?: AbortSignal,
): Promise<PriceDistResponse> {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  const qs = params.toString();
  return getJson<PriceDistResponse>(
    `/api/v1/external/naver/shopping-search/analysis/price-dist${qs ? "?" + qs : ""}`,
    signal,
  );
}

/** GET /api/v1/external/naver/shopping-search/analysis/malls */
export async function getShoppingMallAnalysis(
  query?: string,
  topN = 30,
  signal?: AbortSignal,
): Promise<MallAnalysisResponse> {
  const params = new URLSearchParams({ top_n: String(topN) });
  if (query) params.set("query", query);
  return getJson<MallAnalysisResponse>(
    `/api/v1/external/naver/shopping-search/analysis/malls?${params}`,
    signal,
  );
}

/** GET /api/v1/external/naver/shopping-search/analysis/brands */
export async function getShoppingBrandAnalysis(
  query?: string,
  topN = 20,
  signal?: AbortSignal,
): Promise<BrandAnalysisResponse> {
  const params = new URLSearchParams({ top_n: String(topN) });
  if (query) params.set("query", query);
  return getJson<BrandAnalysisResponse>(
    `/api/v1/external/naver/shopping-search/analysis/brands?${params}`,
    signal,
  );
}

/** GET /api/v1/external/naver/shopping-search/analysis/keywords */
export async function getShoppingKeywordSummary(
  signal?: AbortSignal,
): Promise<KeywordSummaryResponse> {
  return getJson<KeywordSummaryResponse>(
    "/api/v1/external/naver/shopping-search/analysis/keywords",
    signal,
  );
}

/** GET /api/v1/external/naver/shopping-search/analysis/competition?query=... */
export async function getCompetitionScore(
  query: string,
  signal?: AbortSignal,
): Promise<CompetitionScoreResponse> {
  const params = new URLSearchParams({ query });
  return getJson<CompetitionScoreResponse>(
    `/api/v1/external/naver/shopping-search/analysis/competition?${params}`,
    signal,
  );
}

// ── 스마트스토어 수집·조회 ────────────────────────────────────────────────────
export interface SSTableData {
  ok: boolean;
  headers?: string[];
  rows?: string[][];
  collected_at?: string;
  duration_ms?: number;
  error?: string;
  hint?: string;
}

export interface SSStatsData {
  ok: boolean;
  sales_today?: number;
  sales_week?: number;
  sales_month?: number;
  visitors_today?: number;
  orders_today?: number;
  collected_at?: string;
  duration_ms?: number;
  error?: string;
  hint?: string;
}

export async function getSSProducts(signal?: AbortSignal): Promise<SSTableData> {
  return getJson<SSTableData>("/api/v1/smartstore/products", signal);
}
export async function collectSSProducts(limit = 50): Promise<SSTableData> {
  return postJson<SSTableData>(`/api/v1/smartstore/products/collect?limit=${limit}`);
}

// ── 상품 상세 ────────────────────────────────────────────────────────────────

export interface ProductOption {
  option_name: string;
  option_value: string;
  price_diff: number;
  stock: number;
}

export interface ProductDetail {
  product_id: string;
  channel_product_id?: string;
  name?: string;
  status?: string;
  category?: string;
  price?: number;
  original_price?: number;
  stock?: number;
  min_purchase?: number;
  max_purchase?: number;
  main_image_url?: string;
  images?: string[];
  has_options?: boolean;
  options?: ProductOption[];
  delivery_fee?: number;
  view_count?: number;
  order_count?: number;
  review_count?: number;
  review_score?: number;
  detail_url?: string;
  collected_at?: string;
  source?: string;
  _missing_fields?: string[];
}

export interface ProductDetailResponse {
  ok: boolean;
  product?: ProductDetail;
  source?: string;
  collected_at?: string;
  duration_ms?: number;
  error?: string;
  hint?: string;
}

export async function getSSProductDetail(
  productId: string,
  refresh = false,
  signal?: AbortSignal
): Promise<ProductDetailResponse> {
  return getJson<ProductDetailResponse>(
    `/api/v1/smartstore/products/${encodeURIComponent(productId)}?refresh=${refresh}`,
    signal
  );
}

export async function collectSSProductDetail(productId: string): Promise<ProductDetailResponse> {
  return postJson<ProductDetailResponse>(
    `/api/v1/smartstore/products/${encodeURIComponent(productId)}/collect`
  );
}

export type SellerCenterPageKey =
  | "register" | "list" | "dashboard" | "orders" | "settlement" | "reviews" | "stats";

export async function openSellerCenter(pageKey: SellerCenterPageKey): Promise<{
  ok: boolean; page_key?: string; url?: string; message?: string; error?: string; hint?: string;
}> {
  return postJson(`/api/v1/smartstore/open?page_key=${pageKey}`);
}


export async function getSSOrders(signal?: AbortSignal): Promise<SSTableData> {
  return getJson<SSTableData>("/api/v1/smartstore/orders", signal);
}
export async function collectSSOrders(limit = 50): Promise<SSTableData> {
  return postJson<SSTableData>(`/api/v1/smartstore/orders/collect?limit=${limit}`);
}

export async function getSSSettlements(signal?: AbortSignal): Promise<SSTableData> {
  return getJson<SSTableData>("/api/v1/smartstore/settlements", signal);
}
export async function collectSSSettlements(limit = 30): Promise<SSTableData> {
  return postJson<SSTableData>(`/api/v1/smartstore/settlements/collect?limit=${limit}`);
}

export async function getSSReviews(signal?: AbortSignal): Promise<SSTableData> {
  return getJson<SSTableData>("/api/v1/smartstore/reviews", signal);
}
export async function collectSSReviews(limit = 30): Promise<SSTableData> {
  return postJson<SSTableData>(`/api/v1/smartstore/reviews/collect?limit=${limit}`);
}

export async function getSSStats(signal?: AbortSignal): Promise<SSStatsData> {
  return getJson<SSStatsData>("/api/v1/smartstore/stats", signal);
}
export async function collectSSStats(): Promise<SSStatsData> {
  return postJson<SSStatsData>("/api/v1/smartstore/stats/collect");
}

export async function getSSMarketing(signal?: AbortSignal): Promise<SSTableData> {
  return getJson<SSTableData>("/api/v1/smartstore/marketing", signal);
}
export async function collectSSMarketing(): Promise<SSTableData> {
  return postJson<SSTableData>("/api/v1/smartstore/marketing/collect");
}

export interface DescriptionSection {
  key: string;
  label: string;
  required: boolean;
  data_keys: string[];
}

export async function getDescriptionSections(): Promise<{
  ok: boolean;
  sections: DescriptionSection[];
  default_sections: string[];
}> {
  return getJson("/api/v1/smartstore/description/sections");
}

export async function renderDescription(
  sections: string[],
  data: Record<string, unknown>,
): Promise<{ ok: boolean; html?: string; sections?: string[]; error?: string }> {
  return postJson("/api/v1/smartstore/description/render", { sections, data });
}

// 2026-09-24: 앱 런타임 AI 생성 제거 — aiGenerateDescription/gptGenerateDescription
// 호출자는 ProductsClient.tsx에서 정적 안내 문구로 대체됨(백엔드 ai-generate/gpt-generate
// 라우트는 이제 항상 { ok:false } 스텁만 반환하므로 프론트에서 더 이상 호출하지 않는다).

export interface AutoRegisterResult {
  ok: boolean;
  dry_run: boolean;
  steps?: Record<string, { ok: boolean; [k: string]: unknown }>;
  errors?: string[];
  error?: string;
  hint?: string;
}

export interface ProductEditResult {
  ok: boolean;
  product_id?: string;
  dry_run?: boolean;
  steps?: Record<string, { ok: boolean; [k: string]: unknown }>;
  failed_sections?: string[];
  errors?: string[];
  error?: string;
  hint?: string;
}

export async function editProduct(
  productId: string,
  fields: Record<string, unknown>,
  dryRun = true,
): Promise<ProductEditResult> {
  return postJson(`/api/v1/smartstore/products/${encodeURIComponent(productId)}/edit`, {
    fields,
    dry_run: dryRun,
  });
}

export async function autoRegisterProduct(
  data: Record<string, unknown>,
  dryRun = true,
): Promise<AutoRegisterResult> {
  return postJson("/api/v1/smartstore/products/auto-register", { data, dry_run: dryRun });
}

export async function getSettlementsSummary(): Promise<{
  ok: boolean;
  total_rows?: number;
  total_amount?: number;
  total_amount_str?: string;
  collected_at?: string;
  headers?: string[];
  error?: string;
}> {
  return getJson("/api/v1/smartstore/settlements/summary");
}

export async function getSSSettlementsSummary(signal?: AbortSignal) {
  return getSettlementsSummary();
}

// ── CDP 팝업 관리 ──────────────────────────────────────────────────────────

export interface PopupScanResult {
  ok: boolean;
  url?: string;
  found?: number;
  popups?: { selector: string; text: string; has_close_btn: boolean }[];
  error?: string;
}

export interface PopupHandleResult {
  ok: boolean;
  url?: string;
  closed?: number;
  page_clean?: boolean;
  popups_before?: number;
  popups_after?: number;
  detail?: unknown[];
  error?: string;
}

export interface PopupStatusResult {
  ok: boolean;
  watching?: boolean;
  total_events?: number;
  new_tab_count?: number;
  new_window_count?: number;
  layer_count?: number;
  recent_events?: { kind: string; ts: string; handled: boolean; [k: string]: unknown }[];
}

export async function getCategoryCacheInfo(): Promise<{
  ok: boolean; exists?: boolean; count?: number; built_at?: string;
  sample?: { id: string; name: string; path: string; level: number; last: boolean }[];
}> {
  return getJson("/api/v1/smartstore/categories/cache");
}

export async function buildCategoryCache(): Promise<{
  ok: boolean; count?: number; path?: string; error?: string; hint?: string;
}> {
  return postJson("/api/v1/smartstore/categories/cache/build");
}

export async function searchCategories(q: string): Promise<{
  ok: boolean; count?: number; query?: string;
  results?: { id: string; name: string; path: string; level: number; last: boolean }[];
}> {
  return getJson(`/api/v1/smartstore/categories/search?q=${encodeURIComponent(q)}`);
}

export async function popupUnblock(): Promise<{ ok: boolean; methods?: string[]; error?: string }> {
  return postJson("/api/v1/smartstore/popup/unblock");
}

export async function popupScan(): Promise<PopupScanResult> {
  return postJson("/api/v1/smartstore/popup/scan");
}

export async function popupHandle(): Promise<PopupHandleResult> {
  return postJson("/api/v1/smartstore/popup/handle");
}

export async function popupStatus(): Promise<PopupStatusResult> {
  return getJson("/api/v1/smartstore/popup/status");
}

export async function popupPollerStatus(): Promise<{ ok: boolean; running?: boolean; poll_count?: number; interval?: number; error_streak?: number }> {
  return getJson("/api/v1/smartstore/popup/poller");
}

export async function popupPollerStart(interval = 5): Promise<{ ok: boolean; running?: boolean }> {
  return postJson(`/api/v1/smartstore/popup/poller/start?interval=${interval}`);
}

export async function popupPollerStop(): Promise<{ ok: boolean }> {
  return postJson("/api/v1/smartstore/popup/poller/stop");
}

// ── 스마트스토어 AI 에이전트 ──────────────────────────────────────────────────

export type AgentSSEEvent =
  | { event: "start";            data: { prompt: string; confirmed: boolean } }
  | { event: "text";             data: { text: string } }
  | { event: "step_start";       data: { step: number; tool: string; inputs: Record<string, unknown>; write: boolean } }
  | { event: "step_done";        data: { step: number; tool: string; ok: boolean; result: Record<string, unknown> } }
  | { event: "confirm_required"; data: { tool: string; inputs: Record<string, unknown>; message: string } }
  | { event: "done";             data: { steps: number } }
  | { event: "error";            data: { message: string } };

// ── 상세설명 템플릿 ───────────────────────────────────────────────────────────

export interface DescTemplate {
  id: string;
  name: string;
  category: string;
  sections: string[];
  source: string;
  created_at: string;
  data?: Record<string, unknown>;
  html?: string;
}

export async function listDescTemplates(): Promise<{ ok: boolean; templates: DescTemplate[]; count: number }> {
  return getJson("/api/v1/smartstore/description/templates");
}

export async function getDescTemplate(id: string): Promise<{ ok: boolean } & Partial<DescTemplate>> {
  return getJson(`/api/v1/smartstore/description/templates/${id}`);
}

export async function saveDescTemplate(body: {
  name: string; category: string; sections: string[];
  data: Record<string, unknown>; html: string; source: string;
}): Promise<{ ok: boolean; id: string; name: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_AUTH_HEADER) headers["Authorization"] = _AUTH_HEADER;
  const res = await fetch(`${API_BASE}/api/v1/smartstore/description/templates/save`, {
    method: "POST", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteDescTemplate(id: string): Promise<{ ok: boolean }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_AUTH_HEADER) headers["Authorization"] = _AUTH_HEADER;
  const res = await fetch(`${API_BASE}/api/v1/smartstore/description/templates/${id}`, {
    method: "DELETE", headers,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function runSmartStoreAgent(
  prompt: string,
  confirmed: boolean,
  onEvent: (e: AgentSSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_AUTH_HEADER) headers["Authorization"] = _AUTH_HEADER;

  // 백엔드 실제 엔드포인트는 /smartstore/chat (messages 기반). 경로·body 정합.
  return fetch(`${API_BASE}/api/v1/smartstore/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ messages: [{ role: "user", content: prompt }], confirmed, provider: "gpt" }),
    signal,
  }).then(async (res) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";
      for (const part of parts) {
        const eventLine = part.match(/^event: (.+)/m)?.[1]?.trim();
        const dataLine  = part.match(/^data: (.+)/m)?.[1]?.trim();
        if (eventLine && dataLine) {
          try {
            onEvent({ event: eventLine, data: JSON.parse(dataLine) } as AgentSSEEvent);
          } catch { /* ignore malformed */ }
        }
      }
    }
  });
}
