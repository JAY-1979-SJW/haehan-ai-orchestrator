/**
 * Browser task result card (BROWSER-4I)
 *
 * Displays execution result with safe fields only:
 * - Status, action, selector
 * - Execution details (executed, element_found)
 * - Error info if failed
 * - Result summary
 */

import { BrowserTaskResultDisplay } from "@/types/browser-approval";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { RiskBadge } from "@/components/ui/RiskBadge";

interface BrowserTaskResultCardProps {
  result: BrowserTaskResultDisplay;
}

export function BrowserTaskResultCard({
  result,
}: BrowserTaskResultCardProps) {
  const isSuccess = result.status === "executed" && result.result === "success";
  const isFailed = result.status === "failed";

  return (
    <div
      className="rounded-lg border border-[#E5E7EB] bg-white p-4 shadow-sm"
      data-testid={`task-result-${result.task_id}`}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-[13px] font-semibold text-[#111827]">
            {result.action_type}
          </div>
          <div className="mt-1 text-[11px] text-[#6B7280]">
            Task: {result.task_id}
          </div>
        </div>
        <div className="flex gap-2">
          <StatusBadge
            status={result.status}
            label={
              isSuccess
                ? "완료"
                : isFailed
                  ? "실패"
                  : result.status
            }
          />
          <RiskBadge level={result.risk_level} />
        </div>
      </div>

      {/* Execution details */}
      <div className="grid grid-cols-2 gap-3 border-t border-[#F3F4F6] pt-3 text-[12px]">
        <div>
          <div className="text-[#6B7280]">Selector</div>
          <div className="mt-1 font-mono text-[#111827]">{result.selector}</div>
        </div>

        <div>
          <div className="text-[#6B7280]">Domain</div>
          <div className="mt-1 text-[#111827]">
            {result.target_url_domain || "(none)"}
          </div>
        </div>

        <div>
          <div className="text-[#6B7280]">실행됨</div>
          <div className="mt-1 text-[#111827]">
            {result.executed ? "✓ 예" : "✗ 아니오"}
          </div>
        </div>

        <div>
          <div className="text-[#6B7280]">요소 발견</div>
          <div className="mt-1 text-[#111827]">
            {result.element_found ? "✓ 예" : "✗ 아니오"}
          </div>
        </div>

        {result.text_length > 0 && (
          <div>
            <div className="text-[#6B7280]">입력 텍스트</div>
            <div className="mt-1 text-[#111827]">
              {result.text_length} 문자 [REDACTED]
            </div>
          </div>
        )}

        {result.executed_at && (
          <div>
            <div className="text-[#6B7280]">실행 시간</div>
            <div className="mt-1 text-[#111827]">
              {new Date(result.executed_at).toLocaleString("ko-KR")}
            </div>
          </div>
        )}
      </div>

      {/* Result summary */}
      {isSuccess && (
        <div className="mt-3 rounded-md bg-[#ECFDF5] p-2 text-[12px] text-[#059669]">
          ✓ 작업이 성공적으로 완료되었습니다.
        </div>
      )}

      {/* Error details */}
      {isFailed && (
        <div className="mt-3 space-y-2">
          <div className="rounded-md bg-[#FEF2F2] p-2">
            <div className="text-[11px] font-semibold text-[#B91C1C]">
              오류 코드
            </div>
            <div className="mt-1 font-mono text-[12px] text-[#991B1B]">
              {result.error_code || "(unknown)"}
            </div>
          </div>

          {result.error_message && (
            <div className="rounded-md bg-[#FEE2E2] p-2">
              <div className="text-[11px] font-semibold text-[#991B1B]">
                오류 메시지
              </div>
              <div className="mt-1 text-[12px] text-[#991B1B]">
                {result.error_message}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Screenshot reference */}
      {result.screenshot_taken && (
        <div className="mt-3 text-[12px] text-[#6B7280]">
          📷 스크린샷 저장됨{result.screenshot_ref ? ` (${result.screenshot_ref})` : ""}
        </div>
      )}
    </div>
  );
}
