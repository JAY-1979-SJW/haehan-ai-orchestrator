"use client";

import React, { useState } from "react";
import { SubmitApprovalPreviewFixture } from "./__fixtures__/submitApprovalPreview.fixture";
import SubmitPreviewSummary from "./SubmitPreviewSummary";
import SubmitPreviewDetails from "./SubmitPreviewDetails";
import SubmitAuditRecordPanel from "./SubmitAuditRecordPanel";
import {
  createApprovalPayload,
  ApprovalDecisionPayload,
} from "./approvalStatePayload";

type ApprovalState = "pending" | "approved" | "cancelled";

interface SubmitApprovalPanelProps {
  preview: SubmitApprovalPreviewFixture;
  onApprovalDecision?: (payload: ApprovalDecisionPayload) => void;
  showAuditRecord?: boolean;
}

export default function SubmitApprovalPanel({
  preview,
  onApprovalDecision,
  showAuditRecord = false,
}: SubmitApprovalPanelProps) {
  const [state, setState] = useState<ApprovalState>("pending");
  const [showDetails, setShowDetails] = useState(false);

  const handleApprove = () => {
    const payload = createApprovalPayload(
      preview.validation_id,
      preview.preview_hash,
      "approved",
    );
    setState("approved");
    onApprovalDecision?.(payload);
  };

  const handleCancel = () => {
    const payload = createApprovalPayload(
      preview.validation_id,
      preview.preview_hash,
      "cancelled",
    );
    setState("cancelled");
    onApprovalDecision?.(payload);
  };

  const getStatusBadgeStyles = () => {
    switch (state) {
      case "pending":
        return "bg-yellow-100 text-yellow-800 border-yellow-300";
      case "approved":
        return "bg-green-100 text-green-800 border-green-300";
      case "cancelled":
        return "bg-red-100 text-red-800 border-red-300";
    }
  };

  return (
    <div className="flex flex-col bg-slate-900" data-testid="submit-approval-panel">
      {/* 4px 상단 오렌지 accent line */}
      <div className="h-1 w-full bg-orange-500" />

      {/* 메인 카드 */}
      <div className="flex flex-col gap-6 p-6 bg-white rounded-b-[12px] border-l border-r border-b border-slate-200 mx-6 mb-6 mt-4">
        {/* 헤더: 제목 + 상태 배지 */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 className="text-[20px] font-bold text-slate-900 m-0">
              제출 승인 요청
            </h2>
          </div>
          <div
            className={`inline-flex items-center px-3 py-1 rounded-full text-[11px] font-semibold border whitespace-nowrap ${getStatusBadgeStyles()}`}
            data-testid="approval-status-badge"
          >
            {state === "pending" && "대기 중"}
            {state === "approved" && "승인됨"}
            {state === "cancelled" && "취소됨"}
          </div>
        </div>

        {/* Summary layer */}
        <SubmitPreviewSummary summary={preview.user_preview_summary} />

        {/* Details toggle */}
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="text-sm font-medium text-orange-600 hover:text-orange-700 hover:underline transition-colors text-left"
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
        <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-slate-200">
          {state === "pending" && (
            <>
              <button
                onClick={handleApprove}
                className="flex-1 px-4 py-2.5 bg-orange-500 text-white font-semibold text-[13px] rounded-[8px] hover:bg-orange-600 transition-colors cursor-pointer"
                data-testid="approve-button"
              >
                제출 승인
              </button>
              <button
                onClick={handleCancel}
                className="flex-1 px-4 py-2.5 bg-white text-slate-900 font-semibold text-[13px] rounded-[8px] border border-slate-300 hover:bg-slate-50 transition-colors cursor-pointer"
                data-testid="cancel-button"
              >
                취소
              </button>
            </>
          )}
          {state === "approved" && (
            <div
              className="flex-1 px-4 py-2.5 bg-green-100 text-green-800 text-center font-semibold text-[13px] rounded-[8px]"
              data-testid="approved-message"
            >
              ✓ 승인 완료
            </div>
          )}
          {state === "cancelled" && (
            <div
              className="flex-1 px-4 py-2.5 bg-red-100 text-red-800 text-center font-semibold text-[13px] rounded-[8px]"
              data-testid="cancelled-message"
            >
              ✗ 취소됨
            </div>
          )}
        </div>

        {/* Important note for approval state */}
        {state === "approved" && (
          <div
            className="p-3 bg-blue-50 border border-blue-200 rounded-[8px] text-[12px] text-blue-900"
            data-testid="approval-note"
          >
            <strong>알림:</strong> 승인 상태가 저장되었습니다.
            실제 제출은 별도의 승인 절차를 통해 진행됩니다.
          </div>
        )}

        {/* Forbidden: production submit capability notice */}
        <div
          className="p-3 bg-slate-50 border border-slate-300 rounded-[8px] text-[12px] text-slate-700"
          data-testid="production-safeguard-notice"
        >
          <strong>주의:</strong> 이 승인 패널은 관리 목적입니다.
          실제 폼 제출은 독립적인 검증을 거쳐 진행됩니다.
        </div>
      </div>
    </div>
  );
}
