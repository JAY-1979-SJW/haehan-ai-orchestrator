/**
 * 비서앱 MVP read-only API client — APP_UI_SHELL_READONLY_API_WIRING_01
 * 보강: APP_UI_READONLY_BACKEND_STATUS_CARDS_01
 *
 * GET 전용 — POST/PUT/PATCH/DELETE 함수 없음
 * mutation 연결 금지: tasks 실행/approve/reject/execute 없음
 */
import type { ApiConnectionMeta, ErrorKind } from "@/types/assistant";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8400";

// 로컬 개발용 Basic 인증 헤더
const _API_USER = process.env.NEXT_PUBLIC_API_USER ?? "owner";
const _API_PASS = process.env.NEXT_PUBLIC_API_PASS ?? "haehan2024!";
const _AUTH_HEADER = typeof btoa !== "undefined"
  ? `Basic ${btoa(`${_API_USER}:${_API_PASS}`)}`
  : "";

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

async function postJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_AUTH_HEADER) headers["Authorization"] = _AUTH_HEADER;
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, signal });
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
