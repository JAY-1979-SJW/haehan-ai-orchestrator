"use client";
/** /assistant/external-sites — External Sites (APP_EXTERNAL_SITES_READONLY_POLISH_01) */
import { useEffect, useState } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { ProviderCard } from "@/components/assistant/ProviderCard";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { ApiConnectionStateBadge } from "@/components/assistant/ApiConnectionStateBadge";
import { externalProvidersMock } from "@/lib/assistant/mock";
import {
  getAppProviders,
  makeMeta,
  type ApiState,
  type AppProvidersResponse,
} from "@/lib/assistant/api";
import type { ExternalProvider, ActionRisk, ProviderStatus } from "@/types/assistant";

const RISK_MAP: Record<string, ActionRisk> = {
  RISK_CRITICAL: "CRITICAL",
  RISK_HIGH: "HIGH",
  RISK_MEDIUM: "MEDIUM",
  RISK_LOW: "LOW",
  CRITICAL: "CRITICAL",
  HIGH: "HIGH",
  MEDIUM: "MEDIUM",
  LOW: "LOW",
};

const STATUS_MAP: Record<string, ProviderStatus> = {
  STATUS_CURRENT: "CURRENT",
  STATUS_PLANNED: "PLANNED",
  current: "CURRENT",
  planned: "PLANNED",
  CURRENT: "CURRENT",
  PLANNED: "PLANNED",
};

function mapProviders(resp: AppProvidersResponse): ExternalProvider[] {
  return resp.data.providers.map((p) => ({
    id: p.provider_id,
    label: p.display_name,
    risk: RISK_MAP[p.risk_level] ?? "HIGH",
    status: STATUS_MAP[p.current_status] ?? "PLANNED",
    user_present_required: p.user_present_login_required,
    desktop_required: p.desktop_app_required,
    cookie_storage_forbidden: true,
    approval_gate_required: p.approval_gate_required,
    certificate_required: p.certificate_login_required ?? false,
  }));
}

export default function ExternalSitesPage() {
  const [state, setState] = useState<ApiState<AppProvidersResponse>>({ status: "idle" });

  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading" });
    getAppProviders(ctrl.signal)
      .then((data) => setState({ status: "success", data, meta: makeMeta("api") }))
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const isNetwork = (err as Error).message?.includes("fetch");
        setState({
          status: "mock_fallback",
          data: { ok: false, data: { providers: [] }, meta: { provider_count: 0, read_only: true, mutation_allowed: false } },
          meta: makeMeta("mock_fallback", isNetwork ? "network" : "unknown"),
        });
      });
    return () => ctrl.abort();
  }, []);

  const providers: ExternalProvider[] =
    state.status === "success" ? mapProviders(state.data) : externalProvidersMock;

  const loadState =
    state.status === "loading" ? "loading"
    : state.status === "success" ? "success"
    : state.status === "mock_fallback" ? "mock_fallback"
    : "idle";

  const highRisk = providers.filter((p) => p.risk === "HIGH" || p.risk === "CRITICAL").length;
  const needsAuth = providers.filter((p) => p.user_present_required).length;

  return (
    <PageShell title="외부 사이트" description="외부 서비스 연동 현황" chatDomain="ops">
      <div className="space-y-4">
      {/* 헤더 배지 */}
      <div className="flex items-center gap-2 flex-wrap">
        <ApiConnectionStateBadge
          state={loadState}
          meta={state.status === "success" || state.status === "mock_fallback" ? state.meta : undefined}
          label="providers"
        />
        <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-2 py-0.5 rounded">
          {providers.length}개
        </span>
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
      </div>

      <ReadOnlyModeBanner />
      <ForbiddenActionBanner reason="로그인 자동 실행 없음 · 세션 추출 없음 · cookie 저장 없음 — 목록 표시만" />

      {/* mock fallback 배너 */}
      {state.status === "mock_fallback" && (
        <div className="flex items-center gap-2 rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-xs text-[#92400E]">
          <span className="font-mono font-bold">MOCK_FALLBACK</span>
          <span>— API 응답 불가, mock 데이터 표시 중</span>
          <span className="ml-auto font-mono text-[10px]">읽기 전용</span>
        </div>
      )}

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "전체 공급자", value: providers.length, color: "text-[#374151]", bg: "bg-[#F9FAFB]", border: "border-[#E5E7EB]" },
          { label: "HIGH+ 위험", value: highRisk, color: "text-[#B91C1C]", bg: "bg-[#FEF2F2]", border: "border-[#FECACA]" },
          { label: "인증 필요", value: needsAuth, color: "text-[#D97706]", bg: "bg-[#FFFBEB]", border: "border-[#FDE68A]" },
        ].map((card) => (
          <div key={card.label} className={`rounded-lg border ${card.border} ${card.bg} px-3 py-2 text-center`}>
            <div className={`text-lg font-bold font-mono ${card.color}`}>{card.value}</div>
            <div className="text-[10px] text-[#6B7280]">{card.label}</div>
          </div>
        ))}
      </div>

      {/* 공급자 그리드 */}
      {state.status === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          공급자 목록을 불러오는 중…
        </div>
      )}
      {state.status !== "loading" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {providers.map((provider) => (
            <ProviderCard key={provider.id} provider={provider} />
          ))}
        </div>
      )}

      {/* read-only footer */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#9CA3AF] border-t border-[#F3F4F6] pt-2">
        <span>login 없음</span><span>·</span>
        <span>session 추출 없음</span><span>·</span>
        <span>cookie 없음</span><span>·</span>
        <span>접속 버튼 없음</span>
      </div>
      </div>
    </PageShell>
  );
}
