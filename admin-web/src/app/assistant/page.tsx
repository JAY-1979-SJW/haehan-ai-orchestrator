"use client";
/** /assistant — Dashboard (READ_ONLY API wiring) */
import { useEffect, useState } from "react";
import { BackendStatusCard } from "@/components/assistant/BackendStatusCard";
import { StorageStatusCard } from "@/components/assistant/StorageStatusCard";
import { DryRunNotice } from "@/components/assistant/DryRunNotice";
import {
  backendStatusMock, storageStatusMock, knownBacklogMock,
} from "@/lib/assistant/mock";
import {
  getAssistantHealth,
  type ApiState,
  type HealthResponse,
} from "@/lib/assistant/api";
import type { BackendStatus } from "@/types/assistant";

function mergeHealth(
  base: BackendStatus,
  h: HealthResponse,
): BackendStatus {
  return {
    ...base,
    health: h.status === "ok" || h.status === "OK" ? "OK" : "DEGRADED",
    dry_run_gate_enabled:
      h.dry_run_gate_enabled ?? base.dry_run_gate_enabled,
  };
}

export default function AssistantDashboard() {
  const [healthState, setHealthState] = useState<ApiState<HealthResponse>>({
    status: "idle",
  });

  useEffect(() => {
    const ctrl = new AbortController();
    setHealthState({ status: "loading" });
    getAssistantHealth(ctrl.signal)
      .then((data) => {
        setHealthState({ status: "success", data });
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setHealthState({ status: "mock_fallback", data: { status: "MOCK" } });
      });
    return () => ctrl.abort();
  }, []);

  const displayStatus: BackendStatus =
    healthState.status === "success"
      ? mergeHealth(backendStatusMock, healthState.data)
      : healthState.status === "mock_fallback"
      ? backendStatusMock
      : backendStatusMock;

  const isLoading = healthState.status === "loading";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-bold text-[#111827]">대시보드</h1>
        <span className="text-xs font-mono bg-[#F3F4F6] text-[#6B7280] px-2 py-0.5 rounded">
          READ_ONLY
        </span>
        {isLoading && (
          <span className="text-xs text-[#9CA3AF] animate-pulse">
            health 연결 중…
          </span>
        )}
        {healthState.status === "mock_fallback" && (
          <span className="text-xs text-[#F59E0B] font-mono">
            MOCK_FALLBACK
          </span>
        )}
        {healthState.status === "error" && (
          <span className="text-xs text-[#EF4444] font-mono">
            HEALTH_ERROR
          </span>
        )}
      </div>
      <DryRunNotice enabled={displayStatus.dry_run_gate_enabled} />
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
