/** ProviderCard — 외부 사이트 provider 카드 */
import type { ExternalProvider } from "@/types/assistant";
import { RiskBadge } from "@/components/ui/RiskBadge";

export function ProviderCard({ provider }: { provider: ExternalProvider }) {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-3 shadow-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[#111827]">{provider.label}</span>
        <RiskBadge level={provider.risk.toLowerCase() as "low" | "medium" | "high" | "critical"} />
      </div>
      <div className="text-[11px] text-[#6B7280] space-y-0.5">
        {provider.user_present_required && (
          <div className="text-[#D97706]">⚠ 사용자 직접 로그인 필요</div>
        )}
        {provider.desktop_required && (
          <div className="text-[#6B7280]">🖥 데스크톱 전용</div>
        )}
        {provider.cookie_storage_forbidden && (
          <div className="text-[#B91C1C]">🚫 쿠키 저장 금지</div>
        )}
        {provider.approval_gate_required && (
          <div className="text-[#6D28D9]">🔒 게이트 승인 필요</div>
        )}
        {provider.certificate_required && (
          <div className="text-[#1D4ED8]">📜 공인인증 필요</div>
        )}
      </div>
    </div>
  );
}
