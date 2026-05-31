import type { ActionItem } from "../page";
import { RISK_BADGE, STATUS_BADGE } from "./constants";

export function ActionCard({ action }: { action: ActionItem }) {
  return (
    <div className="border border-[#E5E7EB] rounded-lg p-3 bg-white hover:bg-[#F9FAFB] transition-colors">
      <div className="flex items-start gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${RISK_BADGE[action.risk] ?? RISK_BADGE.read}`}>
          {action.risk}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_BADGE[action.status] ?? STATUS_BADGE.planned}`}>
          {action.status}
        </span>
        <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-1.5 py-0.5 rounded border border-[#E5E7EB]">
          {action.action_id}
        </span>
      </div>
      <p className="mt-1.5 text-sm font-medium text-[#111827]">{action.label}</p>
      <p className="text-xs text-[#9CA3AF] font-mono truncate mt-0.5">{action.module}</p>
      {action.required_fields && action.required_fields.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <span className="text-xs text-[#6B7280]">필수:</span>
          {action.required_fields.map((f) => (
            <span key={f} className="text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded">{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}
