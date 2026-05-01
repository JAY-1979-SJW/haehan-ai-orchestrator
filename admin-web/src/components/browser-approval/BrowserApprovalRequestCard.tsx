/**
 * Browser approval request card (BROWSER-4I)
 *
 * Displays a pending browser action approval request with:
 * - Safe fields only (no tokens)
 * - Risk assessment badge
 * - Action details
 * - Final approval warning if needed
 */

import { BrowserApprovalRequestDisplay } from "@/types/browser-approval";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";

interface BrowserApprovalRequestCardProps {
  request: BrowserApprovalRequestDisplay;
}

export function BrowserApprovalRequestCard({
  request,
}: BrowserApprovalRequestCardProps) {
  return (
    <div
      className="rounded-lg border border-[#E5E7EB] bg-white p-4 shadow-sm"
      data-testid={`approval-request-${request.approval_id}`}
    >
      {/* Header with status and approval ID */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-[13px] font-semibold text-[#111827]">
            {request.action_type}
          </div>
          <div className="mt-1 text-[11px] text-[#6B7280]">
            ID: {request.approval_id}
          </div>
        </div>
        <div className="flex gap-2">
          <StatusBadge status={request.status} />
          <RiskBadge level={request.risk_level} />
        </div>
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-3 border-t border-[#F3F4F6] pt-3 text-[12px]">
        <div>
          <div className="text-[#6B7280]">Selector</div>
          <div className="mt-1 font-mono text-[#111827]">{request.selector}</div>
        </div>

        <div>
          <div className="text-[#6B7280]">Domain</div>
          <div className="mt-1 text-[#111827]">
            {request.target_url_domain || "(none)"}
          </div>
        </div>

        {request.text_length !== undefined && (
          <div>
            <div className="text-[#6B7280]">Text Input</div>
            <div className="mt-1 text-[#111827]">
              {request.text_length} characters [REDACTED]
            </div>
          </div>
        )}

        <div>
          <div className="text-[#6B7280]">Requested by</div>
          <div className="mt-1 text-[#111827]">
            {request.requested_by || "(unknown)"}
          </div>
        </div>

        {request.created_at && (
          <div>
            <div className="text-[#6B7280]">Created</div>
            <div className="mt-1 text-[#111827]">
              {new Date(request.created_at).toLocaleString("ko-KR")}
            </div>
          </div>
        )}

        {request.expires_at && (
          <div>
            <div className="text-[#6B7280]">Expires</div>
            <div className="mt-1 text-[#111827]">
              {new Date(request.expires_at).toLocaleString("ko-KR")}
            </div>
          </div>
        )}
      </div>

      {/* Final approval warning */}
      {request.final_approval_required && (
        <div className="mt-3 rounded-md bg-[#FEF3C7] p-2 text-[12px] text-[#92400E]">
          🔒 최종 승인 필요 - 신중한 검토 후 승인하세요
        </div>
      )}

      {/* Risky keywords warning */}
      {request.risky_keywords && request.risky_keywords.length > 0 && (
        <div className="mt-2 rounded-md bg-[#FEE2E2] p-2 text-[12px] text-[#991B1B]">
          ⚠️ 위험한 작업 감지: {request.risky_keywords.join(", ")}
        </div>
      )}

      {/* Expired warning */}
      {request.approval_expired && (
        <div className="mt-2 rounded-md bg-[#F3F4F6] p-2 text-[12px] text-[#6B7280]">
          ⏰ 승인 기간 만료됨
        </div>
      )}

      {/* Already used warning */}
      {request.approval_used && (
        <div className="mt-2 rounded-md bg-[#DBEAFE] p-2 text-[12px] text-[#1D4ED8]">
          ✓ 이미 실행됨
        </div>
      )}
    </div>
  );
}
