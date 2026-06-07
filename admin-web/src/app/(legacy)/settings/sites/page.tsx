"use client";
import { useState, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { fetchSiteCatalog, type CatalogSite } from "@/lib/sitesCatalog";
import { isLocalBridgeAvailable, getEnabledSites, setEnabledSites } from "@/lib/localConfig";

export default function SiteSettingsPage() {
  const [catalog, setCatalog] = useState<CatalogSite[]>([]);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bridgeOk = isLocalBridgeAvailable();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sites, on] = await Promise.all([fetchSiteCatalog(), getEnabledSites()]);
      setCatalog(sites);
      setEnabled(new Set(on));
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = async (siteId: string) => {
    if (!bridgeOk) return;
    const next = new Set(enabled);
    if (next.has(siteId)) next.delete(siteId); else next.add(siteId);
    setEnabled(next);             // 낙관적 반영
    setSaving(siteId);
    try {
      const saved = await setEnabledSites([...next]);  // 로컬 저장
      setEnabled(new Set(saved));
    } catch {
      setEnabled(enabled);        // 실패 시 롤백
      setError("로컬 저장 실패");
    } finally {
      setSaving(null);
    }
  };

  return (
    <PageShell title="사이트 설정" description="내가 사용할 사이트를 선택합니다 (선택·설정은 이 PC에만 저장)" chatDomain="admin">
      <div className="space-y-6">

        {!bridgeOk && (
          <div className="rounded-xl bg-[#FEF9C3] border border-[#FDE68A] px-4 py-3 text-sm text-[#92400E]">
            데스크톱 앱에서만 사이트를 선택·저장할 수 있습니다. (브라우저에서는 목록 보기만 가능)
          </div>
        )}
        {error && (
          <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{error}</div>
        )}

        <div className="flex items-center justify-between">
          <p className="text-sm text-[#6B7280]">
            선택됨 <span className="font-bold text-[#F97316]">{enabled.size}</span> / {catalog.length}개 사이트
          </p>
          <button onClick={load} disabled={loading}
            className="text-xs text-[#6B7280] hover:text-[#111827] disabled:opacity-40">
            {loading ? "불러오는 중..." : "↻ 새로고침"}
          </button>
        </div>

        <div className="grid gap-3">
          {!loading && catalog.length === 0 && (
            <p className="text-sm text-[#9CA3AF] text-center py-10">사용 가능한 사이트가 없습니다 (로그인 필요)</p>
          )}
          {catalog.map((s) => {
            const on = enabled.has(s.site_id);
            return (
              <div key={s.site_id}
                className={`border rounded-xl p-4 flex items-center gap-4 ${on ? "border-[#F97316] bg-[#FFF7ED]" : "border-[#E5E7EB] bg-white"}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-[#111827]">{s.name}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]">{s.category}</span>
                    {s.needs_local_agent && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE]">로컬 에이전트</span>
                    )}
                  </div>
                  <p className="text-xs text-[#9CA3AF] mt-1">{s.work_count}개 작업 지원</p>
                </div>
                <button
                  onClick={() => toggle(s.site_id)}
                  disabled={!bridgeOk || saving === s.site_id}
                  className={`shrink-0 text-sm px-4 py-2 rounded-lg font-semibold disabled:opacity-40 ${
                    on ? "bg-[#F97316] text-white hover:bg-[#EA580C]" : "border border-[#E5E7EB] text-[#374151] hover:bg-[#F3F4F6]"
                  }`}>
                  {saving === s.site_id ? "저장 중..." : on ? "사용 중" : "사용"}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </PageShell>
  );
}
