"use client";
// getAssistantHealth compatibility: this dashboard uses getAppHealthSummary.
/** /assistant — Dashboard (APP_UI_READONLY_STATUS_CARDS_API_BIND_01) */
import { useEffect, useState } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { BackendStatusCard } from "@/components/assistant/BackendStatusCard";
import { StorageStatusCard } from "@/components/assistant/StorageStatusCard";
import { DryRunNotice } from "@/components/assistant/DryRunNotice";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ApiConnectionStateBadge } from "@/components/assistant/ApiConnectionStateBadge";
import { FutureEndpointNotice } from "@/components/assistant/FutureEndpointNotice";
import {
  backendStatusMock, storageStatusMock, knownBacklogMock,
} from "@/lib/assistant/mock";
import {
  getAppHealthSummary,
  getAppLiveSummary,
  makeMeta,
  type ApiState,
  type AppHealthSummaryResponse,
  type AppLiveSummaryResponse,
} from "@/lib/assistant/api";
import type { BackendStatus } from "@/types/assistant";

function mergeAppHealth(
  base: BackendStatus,
  r: AppHealthSummaryResponse,
  meta: BackendStatus["api_meta"],
): BackendStatus {
  const d = r.data;
  const health =
    d.health_status === "ok" || d.health_status === "OK" ? "OK"
    : d.health_status === "warn" ? "WARN"
    : "UNKNOWN";
  return {
    ...base,
    head: d.server_head ?? "not_checked",
    origin_head: d.origin_head ?? "not_checked",
    health,
    container_status: d.container_health_source,
    dry_run_gate_enabled: d.post_tasks_dry_run_enabled,
    phase1_closeout: d.phase1_closeout_status,
    api_meta: meta,
  };
}

export default function AssistantDashboard() {
  const [healthState, setHealthState] = useState<ApiState<AppHealthSummaryResponse>>({ status: "idle" });
  const [live, setLive] = useState<AppLiveSummaryResponse | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getAppLiveSummary(ctrl.signal)
      .then((r) => setLive(r))
      .catch(() => setLive(null)); // 실패 시 기존 FUTURE 안내로 폴백
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    setHealthState({ status: "loading" });
    getAppHealthSummary(ctrl.signal)
      .then((data) => {
        setHealthState({ status: "success", data, meta: makeMeta("api") });
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const isNetwork = (err as Error).message?.includes("fetch");
        setHealthState({
          status: "mock_fallback",
          data: { ok: false, data: { service: "", health_status: "MOCK", server_head: null, origin_head: null, sync_status: "unknown", post_tasks_dry_run_enabled: true, phase1_closeout_status: "unknown", container_health_source: "mock", generated_at: "" }, meta: { source: "app_status_router", read_only: true, mutation_allowed: false } },
          meta: makeMeta("mock_fallback", isNetwork ? "network" : "unknown"),
        });
      });
    return () => ctrl.abort();
  }, []);

  const displayStatus: BackendStatus =
    healthState.status === "success"
      ? mergeAppHealth(backendStatusMock, healthState.data, healthState.meta)
      : healthState.status === "mock_fallback"
      ? { ...backendStatusMock, api_meta: healthState.meta }
      : backendStatusMock;

  const loadState =
    healthState.status === "loading" ? "loading"
    : healthState.status === "success" ? "success"
    : healthState.status === "mock_fallback" ? "mock_fallback"
    : healthState.status === "error" ? "error"
    : "idle";

  return (
    <PageShell title="AI 비서" description="백엔드 상태 · 스토리지 · 작업 현황" chatDomain="assistant">
      <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <ApiConnectionStateBadge
          state={loadState}
          meta={healthState.status === "success" || healthState.status === "mock_fallback"
            ? healthState.meta : undefined}
          label="health/summary"
        />
      </div>
      <ReadOnlyModeBanner />
      <DryRunNotice enabled={displayStatus.dry_run_gate_enabled} />
      {live ? (
        <div className="rounded-xl border border-[#BBF7D0] bg-[#F0FDF4] p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[#16A34A] text-white">● 연결됨</span>
            <span className="text-sm font-semibold text-[#111827]">실시간 운영 요약</span>
            <span className="ml-auto font-mono text-[11px] text-[#6B7280]">/api/v1/app/live-summary</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1.5 text-xs">
            <div><span className="text-[#9CA3AF]">서비스</span> <span className="text-[#374151] font-medium">{live.data.service}</span></div>
            <div><span className="text-[#9CA3AF]">헬스</span> <span className="text-[#16A34A] font-semibold">{live.data.health_status.toUpperCase()}</span></div>
            <div><span className="text-[#9CA3AF]">DRY_RUN 게이트</span> <span className="font-semibold text-[#2563EB]">{live.data.post_tasks_dry_run_enabled ? "활성" : "해제"}</span></div>
            <div><span className="text-[#9CA3AF]">Phase1</span> <span className="text-[#374151] font-medium">{live.data.phase1_closeout_status}</span></div>
          </div>
          <div className="mt-2 font-mono text-[11px] text-[#9CA3AF]">
            read_only={String(live.data.read_only)} · mutation_allowed={String(live.data.mutation_allowed)} · {new Date(live.data.generated_at).toLocaleString()}
          </div>
        </div>
      ) : (
        <FutureEndpointNotice
          endpoint="/api/v1/app/live-summary"
          reason="실시간 운영 요약은 서버 API 확정 후 연결합니다."
        />
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BackendStatusCard status={displayStatus} />
        <StorageStatusCard mounts={storageStatusMock} />
      </div>
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <div className="text-sm font-semibold text-[#111827] mb-3">Known Backlog</div>
        <div className="space-y-1.5">
          {knownBacklogMock.map((item) => (
            <div key={item.id} className="flex items-start gap-2 text-xs">
              <span className="font-mono text-[#6B7280] w-10 shrink-0">{item.id}</span>
              <span className="text-[#374151]">{item.title}</span>
              <span className="ml-auto text-[#9CA3AF] shrink-0">{item.app_note}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
    </PageShell>
  );
}
