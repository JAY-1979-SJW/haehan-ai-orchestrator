"use client";
/** /assistant/storage — Storage Status (APP_UI_READONLY_STATUS_CARDS_API_BIND_01) */
import { useEffect, useState } from "react";
import { StorageStatusCard } from "@/components/assistant/StorageStatusCard";
import { ApiConnectionStateBadge } from "@/components/assistant/ApiConnectionStateBadge";
import { storageStatusMock } from "@/lib/assistant/mock";
import {
  getAppStorageStatus,
  makeMeta,
  type ApiState,
  type AppStorageStatusResponse,
} from "@/lib/assistant/api";
import type { StorageMount, StoragePersistence } from "@/types/assistant";

function mapStorage(resp: AppStorageStatusResponse): StorageMount[] {
  const d = resp.data;
  const mounts: StorageMount[] = [
    {
      label: "운영 스토리지 (named volume)",
      path: d.storage_path,
      persistence: "PERSISTENT" as StoragePersistence,
      description: `${d.audit_log_policy} / ${d.execution_history_policy}`,
    },
    {
      label: "앱 로그 (bind mount)",
      path: d.app_logs_path,
      persistence: "PERSISTENT" as StoragePersistence,
      description: `앱 로그 bind mount (${d.app_logs_bind_mount_status})`,
    },
    {
      label: "런타임 캐시",
      path: "scripts/archive/data/chrome_ui_monitor_state.json",
      persistence: "DISPOSABLE" as StoragePersistence,
      description: `${d.runtime_cache_policy} — KW-1 오류 아님`,
    },
  ];
  return mounts;
}

export default function StorageStatusPage() {
  const [state, setState] = useState<ApiState<AppStorageStatusResponse>>({ status: "idle" });

  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading" });
    getAppStorageStatus(ctrl.signal)
      .then((data) => setState({ status: "success", data, meta: makeMeta("api") }))
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const isNetwork = (err as Error).message?.includes("fetch");
        setState({
          status: "mock_fallback",
          data: { ok: false, data: { storage_paths: [], named_volume_status: "", app_logs_bind_mount_status: "", app_logs_path: "", storage_path: "", audit_log_policy: "", execution_history_policy: "", approval_token_policy: "", runtime_cache_policy: "" }, meta: { read_only: true, mutation_allowed: false } },
          meta: makeMeta("mock_fallback", isNetwork ? "network" : "unknown"),
        });
      });
    return () => ctrl.abort();
  }, []);

  const mounts: StorageMount[] =
    state.status === "success" ? mapStorage(state.data) : storageStatusMock;

  const loadState =
    state.status === "loading" ? "loading"
    : state.status === "success" ? "success"
    : state.status === "mock_fallback" ? "mock_fallback"
    : "idle";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-lg font-bold text-[#111827]">스토리지 상태</h1>
        <ApiConnectionStateBadge
          state={loadState}
          meta={state.status === "success" || state.status === "mock_fallback" ? state.meta : undefined}
          label="storage/status"
        />
      </div>
      <StorageStatusCard mounts={mounts} />
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm text-xs text-[#6B7280] space-y-1">
        <div className="font-semibold text-[#374151]">TTL 정책</div>
        <div>approval_tokens — EPHEMERAL_SECURITY_SENSITIVE_WITH_TTL</div>
        <div>runtime cache — DISPOSABLE (KW-1: 오류 아님)</div>
        <div>execution_history — named volume 영속</div>
      </div>
    </div>
  );
}
