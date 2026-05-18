"use client";
/** /assistant/approval — 승인 게이트 read-only (APP_APPROVAL_GATE_READONLY_POLISH_01) */
import { useState } from "react";
import { GateBadge } from "@/components/assistant/GateBadge";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { approvalGatesMock, knownBacklogMock } from "@/lib/assistant/mock";

export default function ApprovalGatePage() {
  const [showBacklog, setShowBacklog] = useState(false);

  const total = approvalGatesMock.length;
  const blocked = approvalGatesMock.filter((g) => g.current_behavior === "BLOCKED").length;
  const notConnected = approvalGatesMock.filter((g) => g.current_behavior === "NOT_CONNECTED").length;

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-lg font-bold text-[#111827]">승인 게이트</h1>
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
        <span className="text-xs font-mono bg-[#FEF3C7] text-[#92400E] px-2 py-0.5 rounded border border-[#FDE68A]">
          B1_PENDING
        </span>
      </div>

      <ReadOnlyModeBanner />
      <ForbiddenActionBanner reason="approve→execute 미연결 (B-1) — 상태 표시만. 실행 연결 없음" />

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "전체 게이트", value: total, color: "text-[#374151]", bg: "bg-[#F9FAFB]", border: "border-[#E5E7EB]" },
          { label: "BLOCKED", value: blocked, color: "text-[#B91C1C]", bg: "bg-[#FEF2F2]", border: "border-[#FECACA]" },
          { label: "미연결", value: notConnected, color: "text-[#92400E]", bg: "bg-[#FEF3C7]", border: "border-[#FDE68A]" },
        ].map((card) => (
          <div key={card.label} className={`rounded-lg border ${card.border} ${card.bg} px-3 py-2 text-center`}>
            <div className={`text-lg font-bold font-mono ${card.color}`}>{card.value}</div>
            <div className="text-[10px] text-[#6B7280]">{card.label}</div>
          </div>
        ))}
      </div>

      {/* 게이트 테이블 */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[#E5E7EB] text-[10px] text-[#6B7280] uppercase tracking-wide bg-[#F9FAFB]">
              <th className="text-left py-2 px-3">게이트</th>
              <th className="text-left py-2 px-3">위험도</th>
              <th className="text-left py-2 px-3">앱 동작</th>
              <th className="text-left py-2 px-3">자동실행</th>
              <th className="text-left py-2 px-3">현재 상태</th>
            </tr>
          </thead>
          <tbody>
            {approvalGatesMock.map((gate) => (
              <tr key={gate.gate_id} className="border-b border-[#F3F4F6] hover:bg-[#FAFAFA] transition-colors">
                <td className="py-2 px-3 font-mono text-xs text-[#374151]">{gate.gate_id}</td>
                <td className="py-2 px-3">
                  <RiskBadge level={gate.risk_level.toLowerCase() as "low" | "medium" | "high" | "critical"} />
                </td>
                <td className="py-2 px-3">
                  <GateBadge state={gate.state} />
                </td>
                <td className="py-2 px-3 text-xs text-[#B91C1C] font-semibold font-mono">금지</td>
                <td className="py-2 px-3 text-xs text-[#6B7280] font-mono">{gate.current_behavior}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* B-1 안내 패널 */}
      <div className="rounded-xl border border-[#FDE68A] bg-[#FFFBEB] p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono font-bold text-[#92400E]">B-1 PENDING</span>
          <span className="text-[10px] font-mono bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A] px-1.5 py-0.5 rounded">
            INTENTIONAL_INCOMPLETE
          </span>
        </div>
        <p className="text-xs text-[#78350F]">
          approve→execute 연결은 별도 B-1 공정 승인 후 진행됩니다.
          현재 모든 게이트는 <span className="font-mono font-bold">HIDDEN / BLOCKED</span> 상태이며 자동 실행 없음.
        </p>
      </div>

      {/* 알려진 백로그 */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <button
          onClick={() => setShowBacklog((v) => !v)}
          className="text-xs font-semibold text-[#374151] flex items-center gap-1"
        >
          알려진 미완 항목 ({knownBacklogMock.length}개)
          <span className="text-[10px] text-[#9CA3AF]">{showBacklog ? "▲" : "▼"}</span>
        </button>
        {showBacklog && (
          <div className="mt-3 space-y-1">
            {knownBacklogMock.map((b) => (
              <div key={b.id} className="flex items-center gap-2 text-xs text-[#6B7280]">
                <span className="font-mono font-bold text-[#374151] w-10">{b.id}</span>
                <span>{b.title}</span>
                <span className="ml-auto font-mono text-[10px] bg-[#F3F4F6] px-1.5 py-0.5 rounded">
                  {b.app_note}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* read-only footer */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#9CA3AF] border-t border-[#F3F4F6] pt-2">
        <span>execute 없음</span><span>·</span>
        <span>approve 없음</span><span>·</span>
        <span>delete 없음</span><span>·</span>
        <span>token 원문 표시 금지</span><span>·</span>
        <span>B-1 미연결 — 의도된 미완</span>
      </div>
    </div>
  );
}
