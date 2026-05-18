/** /assistant/approval — Approval Gate */
import { GateBadge } from "@/components/assistant/GateBadge";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { approvalGatesMock } from "@/lib/assistant/mock";

export default function ApprovalGatePage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-[#111827]">승인 게이트</h1>
      <ForbiddenActionBanner reason="approve→execute 미연결 (B-1). 상태 표시만" />
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[#E5E7EB] text-xs text-[#6B7280] uppercase">
              <th className="text-left py-2 px-3">게이트</th>
              <th className="text-left py-2 px-3">위험도</th>
              <th className="text-left py-2 px-3">앱 동작</th>
              <th className="text-left py-2 px-3">자동실행</th>
              <th className="text-left py-2 px-3">현재 상태</th>
            </tr>
          </thead>
          <tbody>
            {approvalGatesMock.map((gate) => (
              <tr key={gate.gate_id} className="border-b border-[#F3F4F6]">
                <td className="py-2 px-3 font-mono text-xs">{gate.gate_id}</td>
                <td className="py-2 px-3">
                  <RiskBadge level={gate.risk_level.toLowerCase() as "low"|"medium"|"high"|"critical"} />
                </td>
                <td className="py-2 px-3"><GateBadge state={gate.state} /></td>
                <td className="py-2 px-3 text-xs text-[#B91C1C] font-semibold">금지</td>
                <td className="py-2 px-3 text-xs text-[#6B7280]">{gate.current_behavior}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
