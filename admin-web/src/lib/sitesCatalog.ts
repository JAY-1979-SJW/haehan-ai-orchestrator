/**
 * sitesCatalog.ts — 서버 사이트 카탈로그 조회 (GET /api/v1/sites/catalog).
 * /api/proxy/ 경유로 호출하여 FastAPI URL을 클라이언트에 노출하지 않는다.
 */
import { apiFetch } from "@/lib/api";

export interface CatalogWork {
  work_key: string;
  work_type: string;
  description: string;
  risk_level: string;
  requires_approval: boolean;
  execution_location: string;
}

export interface CatalogSite {
  site_id: string;
  name: string;
  category: string;
  needs_local_agent: boolean;
  work_count: number;
  works: CatalogWork[];
}

interface CatalogResponse {
  sites: CatalogSite[];
}

export async function fetchSiteCatalog(): Promise<CatalogSite[]> {
  const data = await apiFetch<CatalogResponse>("/sites/catalog");
  return Array.isArray(data.sites) ? data.sites : [];
}
