"use client";
// getAssistantHealth compatibility: this dashboard uses getAppHealthSummary.
/** /assistant — Dashboard (APP_UI_READONLY_STATUS_CARDS_API_BIND_01) */
import { useEffect, useState } from "react";
import Link from "next/link";
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
    <PageShell title="AI 비서" description="무엇이든 말로 지시하세요" chatDomain="assistant">
      <div className="space-y-5">
        {/* 소개 */}
        <div className="rounded-2xl border border-[#E5E7EB] bg-white p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F97316] flex items-center justify-center text-white font-bold text-sm">AI</div>
            <div className="min-w-0">
              <h2 className="text-base font-bold text-[#111827]">무엇이든 말로 지시하세요</h2>
              <p className="text-xs text-[#6B7280] mt-0.5">우측 상단 💬 버튼을 눌러 자연어로 요청하면 AI 비서가 알아서 처리합니다.</p>
            </div>
            <span className="ml-auto shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0]">
              {loadState === "error" ? "● 점검 필요" : "● 정상 작동"}
            </span>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {["상품 목록 보여줘", "최근 주문 확인해줘", "리뷰 정리해줘", "Gmail 받은편지함 확인", "EUM 신규현장 알려줘"].map((ex) => (
              <span key={ex} className="text-xs px-3 py-1.5 rounded-full bg-[#F9FAFB] border border-[#E5E7EB] text-[#374151]">{ex}</span>
            ))}
          </div>
        </div>

        {/* 주요 기능 바로가기 */}
        <div>
          <p className="text-sm font-semibold text-[#111827] mb-2">주요 기능</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { href: "/naver/smartstore/products", label: "상품 관리", emoji: "📦" },
              { href: "/naver/smartstore/orders", label: "주문 관리", emoji: "🧾" },
              { href: "/eum", label: "EUM 영업메일", emoji: "📡" },
              { href: "/market-research", label: "시장 조사", emoji: "🔍" },
              { href: "/youtube", label: "YouTube 관리", emoji: "▶️" },
              { href: "/ops", label: "운영센터", emoji: "🛠️" },
            ].map((m) => (
              <Link key={m.href} href={m.href}
                className="rounded-xl border border-[#E5E7EB] bg-white p-4 hover:border-[#F97316] hover:bg-[#FFF7ED] transition-colors">
                <div className="text-2xl mb-1">{m.emoji}</div>
                <div className="text-sm font-semibold text-[#111827]">{m.label}</div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </PageShell>
  );
}
