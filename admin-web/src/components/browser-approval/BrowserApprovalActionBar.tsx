/**
 * Browser approval action bar (BROWSER-4I)
 *
 * Displays approve/reject buttons with proper state management:
 * - Buttons disabled if approval expired/already used/rejected/executed
 * - Approve button disabled if final_approval_required and not confirmed
 * - Reject button always enabled (unless already rejected)
 * - Rejection reason input if rejecting
 * - Final approval checkbox if critical action
 */

"use client";

import { useState } from "react";
import { BrowserApprovalRequestDisplay } from "@/types/browser-approval";
import { Btn } from "@/components/ui/Btn";

interface BrowserApprovalActionBarProps {
  request: BrowserApprovalRequestDisplay;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason?: string) => void;
}

export function BrowserApprovalActionBar({
  request,
  onApprove,
  onReject,
}: BrowserApprovalActionBarProps) {
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [finalApprovalConfirmed, setFinalApprovalConfirmed] = useState(false);

  // Check if buttons should be disabled
  const isDisabled =
    request.approval_expired ||
    request.approval_used ||
    request.status === "rejected" ||
    request.status === "executed" ||
    request.status === "blocked";

  const canApprove =
    request.can_approve &&
    (!request.final_approval_required || finalApprovalConfirmed) &&
    !isDisabled;

  const canReject = request.can_reject && !isDisabled;

  if (isDisabled && request.status !== "rejected") {
    return (
      <div className="text-[12px] text-[#6B7280]">
        승인 불가 상태: {request.status}
      </div>
    );
  }

  if (rejecting) {
    return (
      <div className="space-y-2 rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-3">
        <div>
          <label className="text-[12px] font-semibold text-[#111827]">
            거절 사유
          </label>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="거절 사유를 입력하세요 (선택사항)"
            className="mt-1 w-full rounded border border-[#D1D5DB] px-2 py-1 text-[12px] focus:border-[#1D4ED8] focus:outline-none"
            rows={2}
          />
        </div>
        <div className="flex gap-2">
          <Btn
            variant="danger"
            size="sm"
            onClick={() => {
              onReject(request.approval_id, rejectReason);
              setRejecting(false);
              setRejectReason("");
            }}
          >
            거절 확인
          </Btn>
          <Btn
            variant="secondary"
            size="sm"
            onClick={() => {
              setRejecting(false);
              setRejectReason("");
            }}
          >
            취소
          </Btn>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Final approval checkbox */}
      {request.final_approval_required && (
        <div className="rounded-lg bg-[#FEF3C7] p-2">
          <label className="flex items-start gap-2 text-[12px]">
            <input
              type="checkbox"
              checked={finalApprovalConfirmed}
              onChange={(e) => setFinalApprovalConfirmed(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-[#92400E]">
              이 작업의 위험성을 이해하고 최종 승인합니다.
            </span>
          </label>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        <Btn
          variant="success"
          size="sm"
          disabled={!canApprove}
          onClick={() => onApprove(request.approval_id)}
          title={
            !request.can_approve
              ? "최종 승인이 필요합니다"
              : "승인하기"
          }
        >
          ✓ 승인
        </Btn>
        <Btn
          variant="danger"
          size="sm"
          disabled={!canReject}
          onClick={() => setRejecting(true)}
          title={canReject ? "거절하기" : "거절 불가"}
        >
          ✗ 거절
        </Btn>
      </div>
    </div>
  );
}
