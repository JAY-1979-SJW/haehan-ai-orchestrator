/**
 * localConfig.ts — Electron 로컬 설정 브리지(window.haehanLocal) 가드 래퍼.
 *
 * webview 안에서 실행될 때만 window.haehanLocal 이 존재(P1-3 webview_preload.js).
 * 브라우저(비-Electron)에서는 isLocalBridgeAvailable()=false, 호출은 안전한 기본값 반환.
 * 사이트 선택/설정은 사용자 PC 로컬(config.json)에만 저장 — 서버 전송 없음.
 */

export interface HaehanLocalBridge {
  getEnabledSites: () => Promise<string[]>;
  setEnabledSites: (ids: string[]) => Promise<string[]>;
  getSiteSettings: (siteId: string) => Promise<Record<string, unknown>>;
  setSiteSettings: (siteId: string, settings: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

function bridge(): HaehanLocalBridge | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { haehanLocal?: HaehanLocalBridge };
  return w.haehanLocal ?? null;
}

/** Electron webview(로컬 브리지) 환경인지 여부. */
export function isLocalBridgeAvailable(): boolean {
  return bridge() !== null;
}

export async function getEnabledSites(): Promise<string[]> {
  const b = bridge();
  if (!b) return [];
  try {
    return (await b.getEnabledSites()) ?? [];
  } catch {
    return [];
  }
}

export async function setEnabledSites(ids: string[]): Promise<string[]> {
  const b = bridge();
  if (!b) return [];
  return (await b.setEnabledSites(ids)) ?? [];
}

export async function getSiteSettings(siteId: string): Promise<Record<string, unknown>> {
  const b = bridge();
  if (!b) return {};
  try {
    return (await b.getSiteSettings(siteId)) ?? {};
  } catch {
    return {};
  }
}

export async function setSiteSettings(
  siteId: string,
  settings: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const b = bridge();
  if (!b) return {};
  return (await b.setSiteSettings(siteId, settings)) ?? {};
}
