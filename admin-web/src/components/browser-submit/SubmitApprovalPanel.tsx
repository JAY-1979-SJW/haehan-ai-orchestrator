"use client";

import React, { useState } from "react";
import { SubmitApprovalPreviewFixture } from "./__fixtures__/submitApprovalPreview.fixture";
import SubmitPreviewSummary from "./SubmitPreviewSummary";
import SubmitPreviewDetails from "./SubmitPreviewDetails";
import SubmitAuditRecordPanel from "./SubmitAuditRecordPanel";

/**
 * SubmitApprovalPanel
 *
 * 3-layer submit approval UI:
 * 1. User summary (visible by default)
 * 2. Detailed policy info (collapsible)
 * 3. Audit record (admin/auditor only)
 *
 * State machine:
 * - pending: awaiting user decision
 * - approved: user approved (local state only, no actual submit)
 * - cancelled: user cancelled
 */
type ApprovalState = "pending" | "approved" | "cancelled";

interface SubmitApprovalPanelProps {
  preview: SubmitApprovalPreviewFixture;
  onApprove?: (validationId: string) => void;
  onCancel?: (validationId: string) => void;
  showAuditRecord?: boolean; // Admin/auditor only
}

export default function SubmitApprovalPanel({
  preview,
  onApprove,
  onCancel,
  showAuditRecord = false,
}: SubmitApprovalPanelProps) {
  const [state, setState] = useState<ApprovalState>("pending");
  const [showDetails, setShowDetails] = useState(false);

  const handleApprove = () => {
    setState("approved");
    onApprove?.(preview.validation_id);
  };

  const handleCancel = () => {
    setState("cancelled");
    onCancel?.(preview.validation_id);
  };

  return (
    <div
      className="flex flex-col gap-6 p-6 bg-white rounded-lg border border-gray-200"
      data-testid="submit-approval-panel"
    >
      {/* Top accent bar */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-orange-500" />

      {/* Status badge */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">
          제출 승인 요청
        </h2>
        <div className="px-3 py-1 rounded-full text-sm font-medium" data-testid="approval-status-badge">
          {state === "pending" && (
            <span className="bg-yellow-100 text-yellow-800">대기 중</span>
          )}
          {state === "approved" && (
            <span className="bg-green-100 text-green-800">승인됨</span>
          )}
          {state === "cancelled" && (
            <span className="bg-red-100 text-red-800">취소됨</span>
          )}
        </div>
      </div>

      {/* Summary layer */}
      <SubmitPreviewSummary summary={preview.user_preview_summary} />

      {/* Details toggle */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-sm text-orange-600 hover:text-orange-700 hover:underline"
        data-testid="toggle-details-button"
      >
        {showDetails ? "▼ 자세히 보기" : "▶ 자세히 보기"}
      </button>

      {/* Details layer (collapsible) */}
      {showDetails && (
        <SubmitPreviewDetails details={preview.user_preview_details} />
      )}

      {/* Audit record (admin/auditor only) */}
      {showAuditRecord && (
        <SubmitAuditRecordPanel record={preview.audit_preview_record} />
      )}

      {/* Action buttons */}
      <div className="flex gap-3 pt-4 border-t border-gray-200">
        {state === "pending" && (
          <>
            <button
              onClick={handleApprove}
              className="flex-1 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 font-medium transition"
              data-testid="approve-button"
            >
              제출 승인
            </button>
            <button
              onClick={handleCancel}
              className="flex-1 px-4 py-2 bg-gray-300 text-gray-900 rounded-lg hover:bg-gray-400 font-medium transition"
              data-testid="cancel-button"
            >
              취소
            </button>
          </>
        )}
        {state === "approved" && (
          <div
            className="flex-1 px-4 py-2 bg-green-100 text-green-800 rounded-lg text-center font-medium"
            data-testid="approved-message"
          >
            ✓ 승인 완료
          </div>
        )}
        {state === "cancelled" && (
          <div
            className="flex-1 px-4 py-2 bg-red-100 text-red-800 rounded-lg text-center font-medium"
            data-testid="cancelled-message"
          >
            ✗ 취소됨
          </div>
        )}
      </div>

      {/* Important note for approval state */}
      {state === "approved" && (
        <div
          className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-800"
          data-testid="approval-note"
        >
          <strong>알림:</strong> 승인 상태가 저장되었습니다.
          실제 제출은 별도의 승인 절차를 통해 진행됩니다.
        </div>
      )}

      {/* Forbidden: production submit capability notice */}
      <div
        className="p-3 bg-gray-50 border border-gray-300 rounded text-xs text-gray-700"
        data-testid="production-safeguard-notice"
      >
        <strong>주의:</strong> 이 승인 패널은 관리 목적입니다.
        실제 폼 제출은 독립적인 검증을 거쳐 진행됩니다.
      </div>
    </div>
  );
}
