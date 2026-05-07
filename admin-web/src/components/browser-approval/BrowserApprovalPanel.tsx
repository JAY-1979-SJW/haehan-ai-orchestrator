/**
 * Real Browser Approval Panel (BROWSER-4I)
 *
 * Live approval workflow with real API integration:
 * - Fetches pending approvals from /api/approval/requests
 * - Displays approval request details
 * - Handles approve/reject decisions
 * - Shows approval history
 * - Real API, no mock data
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import { BrowserApprovalRequestCard } from "./BrowserApprovalRequestCard";
import { BrowserApprovalActionBar } from "./BrowserApprovalActionBar";

interface ApprovalRecord {
  approval_event_id: string;
  approval_id: string;
  workflow_run_id: string;
  approval_status: string;
  approval_event_type: string;
  created_at: string;
  target_url_redacted: string;
  target_url_hash: string;
  safe_to_execute: boolean;
  approval_required: boolean;
  decided_by?: string | null;
  decision_reason?: string | null;
  expires_at?: string | null;
}

interface ApprovalState {
  approval: ApprovalRecord;
  decision?: {
    decision: "approve" | "reject";
    reason?: string;
  };
  error?: string;
  isLoading?: boolean;
}

// Stub interface for BrowserApprovalRequestDisplay (mapping)
interface BrowserApprovalRequestDisplay {
  approval_id: string;
  task_id: string;
  status: "received" | "pending" | "approved" | "rejected" | "expired";
  action_type: string;
  selector: string;
  target_url_domain?: string;
  risk_level: string;
  final_approval_required: boolean;
  requested_by?: string;
  created_at?: string;
  expires_at?: string;
  can_approve: boolean;
  can_reject: boolean;
  can_execute: boolean;
  requires_final_approval_input: boolean;
  approval_expired: boolean;
  approval_used: boolean;
}

export function BrowserApprovalPanel() {
  const [approvals, setApprovals] = useState<ApprovalState[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch approvals from real API
  const fetchApprovals = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await fetch("/api/approval/requests");
      if (!response.ok) {
        throw new Error(`Failed to fetch approvals: ${response.statusText}`);
      }

      const data = await response.json();
      if (!data.ok) {
        throw new Error(data.error || "Unknown error");
      }

      // Convert approvals to state format
      const approvalStates: ApprovalState[] = data.approvals.map((approval: ApprovalRecord) => ({
        approval,
      }));

      setApprovals(approvalStates);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      setError(errorMsg);
      console.error("Failed to fetch approvals:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApprovals();
    // Refresh every 10 seconds
    const interval = setInterval(fetchApprovals, 10000);
    return () => clearInterval(interval);
  }, [fetchApprovals]);

  const handleApprove = useCallback(
    async (approvalId: string) => {
      try {
        const response = await fetch(`/api/approval/requests/${approvalId}/approve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decided_by: "admin",
            decided_role: "admin",
            decision_reason: "Approved via UI",
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to approve: ${response.statusText}`);
        }

        const data = await response.json();

        // Update local state
        setApprovals((prev) =>
          prev.map((item) =>
            item.approval.approval_id === approvalId
              ? {
                  ...item,
                  approval: data,
                  decision: { decision: "approve" as const },
                }
              : item
          )
        );
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "Unknown error";
        console.error("Failed to approve:", err);
        setApprovals((prev) =>
          prev.map((item) =>
            item.approval.approval_id === approvalId
              ? { ...item, error: errorMsg }
              : item
          )
        );
      }
    },
    []
  );

  const handleReject = useCallback(
    async (approvalId: string, reason?: string) => {
      try {
        const response = await fetch(`/api/approval/requests/${approvalId}/reject`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decided_by: "admin",
            decided_role: "admin",
            decision_reason: reason || "Rejected via UI",
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to reject: ${response.statusText}`);
        }

        const data = await response.json();

        // Update local state
        setApprovals((prev) =>
          prev.map((item) =>
            item.approval.approval_id === approvalId
              ? {
                  ...item,
                  approval: data,
                  decision: { decision: "reject" as const, reason },
                }
              : item
          )
        );
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "Unknown error";
        console.error("Failed to reject:", err);
        setApprovals((prev) =>
          prev.map((item) =>
            item.approval.approval_id === approvalId
              ? { ...item, error: errorMsg }
              : item
          )
        );
      }
    },
    []
  );

  // Map approval record to UI request display
  const mapToRequestDisplay = (approval: ApprovalRecord): BrowserApprovalRequestDisplay => {
    const isPending = approval.approval_status === "PENDING";
    const isApproved = approval.approval_status === "APPROVED";
    const isRejected = approval.approval_status === "REJECTED";
    const isExpired = approval.approval_status === "EXPIRED";

    return {
      approval_id: approval.approval_id,
      task_id: approval.workflow_run_id, // Use workflow_run_id as task_id for UI
      status: (isPending ? "pending" : isApproved ? "approved" : isRejected ? "rejected" : "expired") as any,
      action_type: "browser.execute_type" as any, // Default action type
      selector: "",
      target_url_domain: approval.target_url_redacted ? new URL(approval.target_url_redacted).hostname : undefined,
      risk_level: "medium",
      final_approval_required: false,
      requested_by: "system",
      created_at: approval.created_at,
      expires_at: approval.expires_at || undefined,
      can_approve: isPending,
      can_reject: isPending,
      can_execute: false, // Always false per policy
      requires_final_approval_input: false,
      approval_expired: isExpired,
      approval_used: isApproved,
    } as BrowserApprovalRequestDisplay;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-[18px] font-bold text-[#111827]">
          브라우저 작업 승인
        </h2>
        <p className="mt-1 text-[12px] text-[#6B7280]">
          실제 API를 사용한 승인 워크플로우 관리
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="rounded-lg bg-[#FEE2E2] p-3 text-[12px] text-[#991B1B]">
          <strong>⚠️ 오류:</strong> {error}
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="rounded-lg bg-[#EFF6FF] p-3 text-[12px] text-[#1D4ED8]">
          <strong>📋 로딩 중...</strong> 승인 요청을 불러오고 있습니다.
        </div>
      )}

      {/* Empty state */}
      {!isLoading && approvals.length === 0 && !error && (
        <div className="rounded-lg bg-[#F0FDF4] p-3 text-[12px] text-[#166534]">
          <strong>✓ 완료:</strong> 처리 대기 중인 승인 요청이 없습니다.
        </div>
      )}

      {/* Approvals list */}
      <div className="space-y-4">
        {approvals.map((item) => {
          const isPending = item.approval.approval_status === "PENDING";
          const isApproved = item.approval.approval_status === "APPROVED";
          const isRejected = item.approval.approval_status === "REJECTED";

          const requestDisplay = mapToRequestDisplay(item.approval);

          return (
            <div
              key={item.approval.approval_id}
              className="rounded-lg border border-[#E5E7EB] bg-white p-4"
            >
              {/* Request card */}
              <BrowserApprovalRequestCard request={requestDisplay as any} />

              {/* Approval details */}
              <div className="mt-3 rounded-md bg-[#F9FAFB] p-3 text-[11px] space-y-1 border border-[#F3F4F6]">
                <div>
                  <span className="font-semibold text-[#374151]">Approval ID:</span>
                  <span className="ml-2 font-mono text-[#6B7280]">
                    {item.approval.approval_id.substring(0, 20)}...
                  </span>
                </div>
                <div>
                  <span className="font-semibold text-[#374151]">URL Hash:</span>
                  <span className="ml-2 font-mono text-[#6B7280]">
                    {item.approval.target_url_hash.substring(0, 16)}...
                  </span>
                </div>
                <div>
                  <span className="font-semibold text-[#374151]">Safe to Execute:</span>
                  <span className="ml-2 text-[#DC2626]">
                    {item.approval.safe_to_execute ? "true (⚠️)" : "false (✓)"}
                  </span>
                </div>
              </div>

              {/* Action bar (if pending) */}
              {isPending && !item.error && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <BrowserApprovalActionBar
                    request={requestDisplay as any}
                    onApprove={handleApprove}
                    onReject={handleReject}
                  />
                </div>
              )}

              {/* Error message */}
              {item.error && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <div className="rounded-md bg-[#FEE2E2] p-2 text-[11px] text-[#991B1B]">
                    <strong>오류:</strong> {item.error}
                  </div>
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
                          <div className="text-[#6B7280] text-[11px]">
                            사유: {item.decision.reason}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Rejected state */}
              {isRejected && !item.decision && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <div className="text-[12px] text-[#6B7280]">
                    이 승인은 거절되었습니다.
                  </div>
                </div>
              )}

              {/* Approved state */}
              {isApproved && !item.decision && (
                <div className="mt-4 border-t border-[#F3F4F6] pt-4">
                  <div className="flex items-center gap-2 rounded-md bg-[#ECFDF5] p-2 text-[12px] text-[#059669]">
                    <span>✓</span>
                    <span>승인됨</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer info */}
      <div className="rounded-lg bg-[#EFF6FF] p-3 text-[12px] text-[#1D4ED8]">
        <strong>ℹ️ 정보:</strong> 이 컴포넌트는 실제 API를 사용합니다.
        Approval ID와 URL Hash는 공개 정보입니다.
        <br />
        <strong>보안:</strong> safe_to_execute는 항상 false이며, 승인 여부와 관계없이
        실행 권한을 주지 않습니다.
      </div>
    </div>
  );
}
