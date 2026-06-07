"use client";
/** /assistant/deployment — Deployment Status (APP_DEPLOYMENT_READONLY_POLISH_01)
 * restart/compose 버튼 없음, server_apply_allowed=false
 */
import { useState, useEffect } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { DeploymentSopPanel } from "@/components/assistant/DeploymentSopPanel";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { deploymentStatusMock } from "@/lib/assistant/mock";
import { getAppDeploymentStatus } from "@/lib/assistant/api";

export default function DeploymentStatusPage() {
  const [showSop, setShowSop] = useState(true);
  const [status, setStatus] = useState(deploymentStatusMock);

  // /api/v1/app/deployment-status 연결 (실패 시 mock 유지)
  useEffect(() => {
    const ctrl = new AbortController();
    getAppDeploymentStatus(ctrl.signal)
      .then((r) => setStatus({
        server_head: r.data.server_head ?? "—",
        origin_head: r.data.origin_head ?? "—",
        state: r.data.state,
        build_required: r.data.build_required,
        sop_steps: r.data.sop_steps,
      } as typeof deploymentStatusMock))
      .catch(() => { /* mock 유지 */ });
    return () => ctrl.abort();
  }, []);

  const isSynced = status.state === "SYNCED";

  return (
    <PageShell title="배포 현황" description="서버 배포 상태 · SOP" chatDomain="ops">
      <div className="space-y-4">
      {/* 헤더 배지 */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-mono bg-[#FEF3C7] text-[#92400E] px-2 py-0.5 rounded border border-[#FDE68A]">
          server_apply_allowed=false
        </span>
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
      </div>

      <ReadOnlyModeBanner />
      <ForbiddenActionBanner reason="서버 재시작 / docker compose 버튼 없음 — 조회 전용" />

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2">
        {[
          {
            label: "서버 HEAD",
            value: status.server_head ?? "—",
            color: "text-[#374151]",
            bg: "bg-[#F9FAFB]",
            border: "border-[#E5E7EB]",
          },
          {
            label: "동기화 상태",
            value: status.state,
            color: isSynced ? "text-[#059669]" : "text-[#B91C1C]",
            bg: isSynced ? "bg-[#F0FDF4]" : "bg-[#FEF2F2]",
            border: isSynced ? "border-[#BBF7D0]" : "border-[#FECACA]",
          },
          {
            label: "빌드 필요",
            value: status.build_required ? "YES" : "NO",
            color: status.build_required ? "text-[#B91C1C]" : "text-[#059669]",
            bg: status.build_required ? "bg-[#FEF2F2]" : "bg-[#F0FDF4]",
            border: status.build_required ? "border-[#FECACA]" : "border-[#BBF7D0]",
          },
        ].map((card) => (
          <div key={card.label} className={`rounded-lg border ${card.border} ${card.bg} px-3 py-2 text-center`}>
            <div className={`text-sm font-bold font-mono truncate ${card.color}`}>{card.value}</div>
            <div className="text-[10px] text-[#6B7280]">{card.label}</div>
          </div>
        ))}
      </div>

      {/* SOP 안내 */}
      <div className="rounded-xl border border-[#DBEAFE] bg-[#EFF6FF] p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono font-bold text-[#1D4ED8]">BAKED_IN_IMAGE SOP</span>
          <span className="text-[10px] font-mono bg-[#DBEAFE] text-[#1E40AF] border border-[#BFDBFE] px-1.5 py-0.5 rounded">
            RESTART_ALONE_FORBIDDEN
          </span>
          <button
            onClick={() => setShowSop((v) => !v)}
            className="ml-auto text-[10px] text-[#3B82F6] hover:underline font-mono"
          >
            {showSop ? "접기" : "펼치기"}
          </button>
        </div>
        {showSop && (
          <ol className="space-y-1 mt-2">
            {status.sop_steps.map((step, i) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                <span className="font-mono font-bold text-[#1D4ED8] w-5">{i + 1}.</span>
                <code className="bg-white border border-[#BFDBFE] px-2 py-0.5 rounded text-[11px] text-[#1E3A8A]">
                  {step}
                </code>
              </li>
            ))}
          </ol>
        )}
        <p className="text-[10px] text-[#1D4ED8] mt-2 font-mono">
          restart 단독 금지 — 반드시 build 후 up -d
        </p>
      </div>

      {/* 배포 상태 패널 */}
      <DeploymentSopPanel status={status} />

      {/* read-only footer */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#9CA3AF] border-t border-[#F3F4F6] pt-2">
        <span>restart 없음</span><span>·</span>
        <span>compose 없음</span><span>·</span>
        <span>force-push 없음</span><span>·</span>
        <span>server_apply_allowed=false</span>
      </div>
      </div>
    </PageShell>
  );
}
