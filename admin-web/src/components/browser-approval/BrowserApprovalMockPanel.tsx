/**
 * Browser approval mock panel (BROWSER-4I)
 *
 * Demo/test component that shows browser approval workflow with mock data:
 * - List of pending approvals
 * - Approval request cards
 * - Action bars (approve/reject)
 * - Result cards
 * - Mock state management (no real API)
 */

"use client";

import { useState } from "react";
import {
  BrowserApprovalRequestDisplay,
  BrowserTaskResultDisplay,
  MOCK_BROWSER_APPROVAL_REQUESTS,
  MOCK_BROWSER_TASK_RESULTS,
} from "@/types/browser-approval";
import { BrowserApprovalRequestCard } from "./BrowserApprovalRequestCard";
import { BrowserApprovalActionBar } from "./BrowserApprovalActionBar";
import { BrowserTaskResultCard } from "./BrowserTaskResultCard";

interface ApprovalState {
  request: BrowserApprovalRequestDisplay;
  result?: BrowserTaskResultDisplay;
  decision?: {
    decision: "approve" | "reject";
    reason?: string;
  };
}

export function BrowserApprovalMockPanel() {
  const [approvals, setApprovals] = useState<ApprovalState[]>(
    MOCK_BROWSER_APPROVAL_REQUESTS.map((req) => ({
      request: req,
      result: MOCK_BROWSER_TASK_RESULTS.find((r) => r.task_id === req.task_id),
    }))
  );

  const handleApprove = (approvalId: string) => {
    setApprovals((prev) =>
      prev.map((item) =>
        item.request.approval_id === approvalId
          ? {
              ...item,
              request: {
                ...item.request,
                status: "approved" as const,
              },
              decision: {
                decision: "approve" as const,
              },
            }
          : item
      )
    );
  };

  const handleReject = (approvalId: string, reason?: string) => {
    setApprovals((prev) =>
      prev.map((item) =>
        item.request.approval_id === approvalId
          ? {
              ...item,
              request: {
                ...item.request,
                status: "rejected" as const,
              },
              decision: {
                decision: "reject" as const,
                reason,
              },
            }
          : item
      )
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-[18px] font-bold text-[#111827]">
          브라우저 작업 승인 (Mock)
        </h2>
        <p className="mt-1 text-[12px] text-[#6B7280]">
          Mock 데이터를 사용한 승인 워크플로우 테스트
        </p>
      </div>

      {/* Approvals list */}
      <div className="space-y-4">
        {approvals.map((item) => {
          const isPending =
            item.request.status === "received" ||
            item.request.status === "pending";
          const isExecuted = item.request.status === "approved";
          const isRejected = item.request.status === "rejected";

          return (
            <div
              key={item.request.approval_id}
              className="rounded-lg border border-[#E5E7EB] bg-white p-4"
            >
              {/* Request card */}
              <BrowserApprovalRequestCard request={item.request} />

              {/* Action bar (if pending) */}
              {isPending && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <BrowserApprovalActionBar
                    request={item.request}
                    onApprove={handleApprove}
                    onReject={handleReject}
                  />
                </div>
              )}

              {/* Decision info */}
              {item.decision && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <div className="text-[12px]">
                    {item.decision.decision === "approve" ? (
                      <div className="flex items-center gap-2 rounded-md bg-[#ECFDF5] p-2 text-[#059669]">
                        <span>✓</span>
                        <span>승인됨</span>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 rounded-md bg-[#FEF2F2] p-2 text-[#B91C1C]">
                          <span>✗</span>
                          <span>거절됨</span>
                        </div>
                        {item.decision.reason && (
                          <div className="text-[#6B7280]">
                            사유: {item.decision.reason}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Result card (if executed) */}
              {isExecuted && item.result && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <BrowserTaskResultCard result={item.result} />
                </div>
              )}

              {/* Rejected state */}
              {isRejected && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <div className="text-[12px] text-[#6B7280]">
                    이 승인은 거절되었습니다.
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer info */}
      <div className="rounded-lg bg-[#EFF6FF] p-3 text-[12px] text-[#1D4ED8]">
        <strong>ℹ️ Mock 정보:</strong> 이 컴포넌트는 mock 데이터를 사용합니다.
        실제 API 호출이 없으며, 로컬 상태만 변경됩니다.
        <br />
        <strong>보안:</strong> approval_token, final_approval_token, token_hash는
        UI에 표시되지 않습니다.
      </div>
    </div>
  );
}
