"use client";
/** /assistant/external-sites — External Sites (APP_UI_READONLY_STATUS_CARDS_API_BIND_01) */
import { useEffect, useState } from "react";
import { ProviderCard } from "@/components/assistant/ProviderCard";
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
    state.status === "success"
      ? mapProviders(state.data)
      : externalProvidersMock;

  const loadState =
    state.status === "loading" ? "loading"
    : state.status === "success" ? "success"
    : state.status === "mock_fallback" ? "mock_fallback"
    : "idle";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-lg font-bold text-[#111827]">외부 사이트 ({providers.length}개)</h1>
        <ApiConnectionStateBadge
          state={loadState}
          meta={state.status === "success" || state.status === "mock_fallback" ? state.meta : undefined}
          label="providers"
        />
      </div>
      <ForbiddenActionBanner reason="최종 제출 / 결제 / DNS 저장 / 인증서 서명 버튼 없음" />
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {providers.map((provider) => (
          <ProviderCard key={provider.id} provider={provider} />
        ))}
      </div>
    </div>
  );
}
