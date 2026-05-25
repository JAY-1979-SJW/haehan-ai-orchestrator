"use client";
// getAssistantHealth compatibility: this dashboard uses getAppHealthSummary.
/** /assistant — Dashboard (APP_UI_READONLY_STATUS_CARDS_API_BIND_01) */
import { useEffect, useState } from "react";
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
  makeMeta,
  type ApiState,
  type AppHealthSummaryResponse,
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
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-lg font-bold text-[#111827]">대시보드</h1>
        <ApiConnectionStateBadge
          state={loadState}
          meta={healthState.status === "success" || healthState.status === "mock_fallback"
            ? healthState.meta : undefined}
          label="health/summary"
        />
      </div>
      <ReadOnlyModeBanner />
      <DryRunNotice enabled={displayStatus.dry_run_gate_enabled} />
      <FutureEndpointNotice
        endpoint="/api/v1/app/live-summary"
        reason="실시간 운영 요약은 서버 API 확정 후 연결합니다."
      />
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
  );
}
