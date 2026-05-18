"use client";
/** /assistant — Dashboard (READ_ONLY status cards 보강) */
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
  getAssistantHealth,
  makeMeta,
  type ApiState,
  type HealthResponse,
} from "@/lib/assistant/api";
import type { BackendStatus } from "@/types/assistant";

function mergeHealth(base: BackendStatus, h: HealthResponse, meta: BackendStatus["api_meta"]): BackendStatus {
  return {
    ...base,
    health: h.status === "ok" || h.status === "OK" ? "OK" : "DEGRADED",
    dry_run_gate_enabled: h.dry_run_gate_enabled ?? base.dry_run_gate_enabled,
    api_meta: meta,
  };
}

export default function AssistantDashboard() {
  const [healthState, setHealthState] = useState<ApiState<HealthResponse>>({ status: "idle" });

  useEffect(() => {
    const ctrl = new AbortController();
    setHealthState({ status: "loading" });
    getAssistantHealth(ctrl.signal)
      .then((data) => {
        setHealthState({ status: "success", data, meta: makeMeta("api") });
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const isNetwork = (err as Error).message?.includes("fetch");
        setHealthState({
          status: "mock_fallback",
          data: { status: "MOCK" },
          meta: makeMeta("mock_fallback", isNetwork ? "network" : "unknown"),
        });
      });
    return () => ctrl.abort();
  }, []);

  const displayStatus: BackendStatus =
    healthState.status === "success"
      ? mergeHealth(backendStatusMock, healthState.data, healthState.meta)
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
          label="health"
        />
      </div>
      <ReadOnlyModeBanner />
      <DryRunNotice enabled={displayStatus.dry_run_gate_enabled} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BackendStatusCard status={displayStatus} />
        <StorageStatusCard mounts={storageStatusMock} />
      </div>
      <FutureEndpointNotice
        endpoint="GET /api/v1/storage/status"
        reason="스토리지 실시간 상태는 향후 공정에서 연결될 예정입니다."
      />
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
