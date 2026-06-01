/**
 * sitesCatalog.ts — 서버 사이트 카탈로그 조회 (GET /api/v1/sites/catalog).
 * JWT 인증 필요(get_jwt_user) → userAuth 토큰을 Bearer 로 전달.
 */
import { getToken } from "@/lib/userAuth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8401";

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

export async function fetchSiteCatalog(): Promise<CatalogSite[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/v1/sites/catalog`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`카탈로그 조회 실패 (${res.status})`);
  const data = await res.json();
  return Array.isArray(data.sites) ? data.sites : [];
}
