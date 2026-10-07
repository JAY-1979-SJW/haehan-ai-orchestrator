// 마케팅 운영 기능 스위치 — 서버 API(GET /naver/marketing-ops/settings, POST …/settings/toggle; admin·owner)를
// 공용 프록시(/api/proxy)로 호출한다. 새 서버 API 는 만들지 않는다. 인증은 userAuth.ts 와 같은 방식(저장된 토큰을 Bearer 로).
import { getToken } from "@/lib/userAuth";

const API_BASE = "/api/proxy/api/v1/naver/marketing-ops";

export interface MarketingOpsSettings {
  ok: boolean;
  enabled: boolean;
}

function headers(): HeadersInit {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function parse(res: Response): Promise<MarketingOpsSettings> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "";
    throw new Error(res.status === 403 ? "관리자(관리자·오너)만 바꿀 수 있습니다" : detail || `요청 실패 (${res.status})`);
  }
  return { ok: true, enabled: data.enabled === true };
}

export async function getMarketingOpsSettings(): Promise<MarketingOpsSettings> {
  return parse(await fetch(`${API_BASE}/settings`, { headers: headers(), cache: "no-store" }));
}

export async function setMarketingOpsEnabled(enabled: boolean): Promise<MarketingOpsSettings> {
  return parse(
    await fetch(`${API_BASE}/settings/toggle`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ enabled }),
    }),
  );
}
