"use client";
/** /assistant/storage — Storage Status (APP_STORAGE_READONLY_POLISH_01) */
import { useEffect, useState } from "react";
import { StorageStatusCard } from "@/components/assistant/StorageStatusCard";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
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
  return [
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
          data: {
            ok: false,
            data: {
              storage_paths: [], named_volume_status: "", app_logs_bind_mount_status: "",
              app_logs_path: "", storage_path: "", audit_log_policy: "",
              execution_history_policy: "", approval_token_policy: "", runtime_cache_policy: "",
            },
            meta: { read_only: true, mutation_allowed: false },
          },
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

  const persistent = mounts.filter((m) => m.persistence === "PERSISTENT").length;
  const disposable = mounts.filter((m) => m.persistence === "DISPOSABLE").length;

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-lg font-bold text-[#111827]">스토리지 상태</h1>
        <ApiConnectionStateBadge
          state={loadState}
          meta={state.status === "success" || state.status === "mock_fallback" ? state.meta : undefined}
          label="storage/status"
        />
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
      </div>

      <ReadOnlyModeBanner />

      {/* mock fallback 배너 */}
      {state.status === "mock_fallback" && (
        <div className="flex items-center gap-2 rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-xs text-[#92400E]">
          <span className="font-mono font-bold">MOCK_FALLBACK</span>
          <span>— API 응답 불가, mock 데이터 표시 중</span>
          <span className="ml-auto font-mono text-[10px]">read_only=true</span>
        </div>
      )}

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "마운트 수", value: mounts.length, color: "text-[#374151]", bg: "bg-[#F9FAFB]", border: "border-[#E5E7EB]" },
          { label: "PERSISTENT", value: persistent, color: "text-[#059669]", bg: "bg-[#F0FDF4]", border: "border-[#BBF7D0]" },
          { label: "DISPOSABLE", value: disposable, color: "text-[#D97706]", bg: "bg-[#FFFBEB]", border: "border-[#FDE68A]" },
        ].map((card) => (
          <div key={card.label} className={`rounded-lg border ${card.border} ${card.bg} px-3 py-2 text-center`}>
            <div className={`text-lg font-bold font-mono ${card.color}`}>{card.value}</div>
            <div className="text-[10px] text-[#6B7280]">{card.label}</div>
          </div>
        ))}
      </div>

      {/* 로딩 */}
      {state.status === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          스토리지 상태를 불러오는 중…
        </div>
      )}

      {state.status !== "loading" && <StorageStatusCard mounts={mounts} />}

      {/* TTL 정책 */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm text-xs text-[#6B7280] space-y-1">
        <div className="font-semibold text-[#374151]">TTL 정책</div>
        <div>approval_tokens — EPHEMERAL_SECURITY_SENSITIVE_WITH_TTL</div>
        <div>runtime cache — DISPOSABLE (KW-1: 오류 아님)</div>
        <div>execution_history — named volume 영속</div>
      </div>

      {/* B-3 감사 미완 안내 */}
      <div className="rounded-xl border border-[#FDE68A] bg-[#FFFBEB] p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono font-bold text-[#92400E]">B-3 AUDIT_PENDING</span>
          <span className="text-[10px] font-mono bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A] px-1.5 py-0.5 rounded">
            READ_ONLY
          </span>
        </div>
        <p className="text-xs text-[#78350F]">
          approval_tokens 금고는 잠금 상태입니다. 감사 공정(B-3) 완료 전까지 token 원문 표시 금지.
        </p>
      </div>

      {/* read-only footer */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#9CA3AF] border-t border-[#F3F4F6] pt-2">
        <span>delete 없음</span><span>·</span>
        <span>format 없음</span><span>·</span>
        <span>mount 변경 없음</span><span>·</span>
        <span>token 원문 금지</span>
      </div>
    </div>
  );
}
