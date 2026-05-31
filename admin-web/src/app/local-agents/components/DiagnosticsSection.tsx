import type { LocalAgentDiagnostics } from "@/types/local-agent";

export function LoadingRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-8 text-center text-[13px] text-[#6B7280]">
        불러오는 중…
      </td>
    </tr>
  );
}

export function DiagnosticsSection({
  diagnostics,
  error,
}: {
  diagnostics: LocalAgentDiagnostics | null;
  error: string | null;
}) {
  if (!diagnostics && !error) return null;

  if (error) {
    return (
      <div className="mb-6 px-4 py-3 rounded-[8px] border border-[#FEE2E2] bg-[#FEF2F2] text-[12px] text-[#B91C1C]">
        {error}
      </div>
    );
  }

  if (!diagnostics) return null;

  const statusColor = {
    ok: "bg-[#D1FAE5] text-[#065F46]",
    warn: "bg-[#FEF3C7] text-[#92400E]",
    error: "bg-[#FEE2E2] text-[#B91C1C]",
  }[diagnostics.status] || "bg-[#F3F4F6] text-[#6B7280]";

  const repoBoundaryColor = {
    pass: "bg-[#D1FAE5] text-[#065F46]",
    fail: "bg-[#FEE2E2] text-[#B91C1C]",
    not_checked: "bg-[#F3F4F6] text-[#6B7280]",
  }[diagnostics.repo_boundary_status] || "bg-[#F3F4F6] text-[#6B7280]";

  const waitingApprovalColor = diagnostics.tasks.waiting_approval > 0 ? "text-[#B91C1C]" : "";
  const failedColor = diagnostics.tasks.failed > 0 ? "text-[#B91C1C]" : "";

  return (
    <div className="mb-6">
      <div className="text-[13px] font-bold text-[#0F172A] mb-4">운영 진단</div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">상태</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">진단 상태</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${statusColor}`}>
                {diagnostics.status}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">Repo Boundary</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${repoBoundaryColor}`}>
                {diagnostics.repo_boundary_status}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">에이전트 상태</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">전체</span>
              <span className="text-[13px] font-semibold">{diagnostics.agents.total}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">온라인</span>
              <span className="text-[13px] font-semibold text-[#059669]">{diagnostics.agents.online}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">오프라인/응답지연</span>
              <span className="text-[13px] font-semibold text-[#9CA3AF]">
                {diagnostics.agents.offline + diagnostics.agents.stale}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">작업 상태</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">전체</span>
              <span className="text-[13px] font-semibold">{diagnostics.tasks.total}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">실행중</span>
              <span className="text-[13px] font-semibold text-[#F97316]">{diagnostics.tasks.running}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-[12px] text-[#6B7280] ${waitingApprovalColor ? "font-semibold" : ""}` }>
                승인대기
              </span>
              <span className={`text-[13px] font-semibold ${waitingApprovalColor}`}>
                {diagnostics.tasks.waiting_approval}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-[12px] text-[#6B7280] ${failedColor ? "font-semibold" : ""}` }>
                실패
              </span>
              <span className={`text-[13px] font-semibold ${failedColor}`}>
                {diagnostics.tasks.failed}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">완료</span>
              <span className="text-[13px] font-semibold text-[#059669]">{diagnostics.tasks.completed}</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">요약 정보</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">결과 요약</span>
              <span className="text-[13px] font-semibold">{diagnostics.summaries.with_result_summary}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">관찰 요약</span>
              <span className="text-[13px] font-semibold">{diagnostics.summaries.with_observe_summary}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">감사 요약</span>
              <span className="text-[13px] font-semibold">{diagnostics.summaries.with_audit_summary}</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">최근 작업</div>
          <div className="space-y-2 text-[11px]">
            {diagnostics.latest.task_status && (
              <div className="flex items-center justify-between">
                <span className="text-[#6B7280]">상태</span>
                <span className="font-semibold">{diagnostics.latest.task_status}</span>
              </div>
            )}
            {diagnostics.latest.task_created_at && (
              <div className="flex items-center justify-between">
                <span className="text-[#6B7280]">생성</span>
                <span className="font-mono text-[10px]">{diagnostics.latest.task_created_at.split("T")[0]}</span>
              </div>
            )}
            {diagnostics.latest.task_updated_at && (
              <div className="flex items-center justify-between">
                <span className="text-[#6B7280]">업데이트</span>
                <span className="font-mono text-[10px]">{diagnostics.latest.task_updated_at.split("T")[0]}</span>
              </div>
            )}
          </div>
        </div>

        {diagnostics.warnings.length > 0 && (
          <div className="bg-white border border-[#FEE2E2] rounded-[8px] p-4">
            <div className="text-[11px] font-semibold text-[#B91C1C] mb-3">경고</div>
            <div className="flex flex-wrap gap-1.5">
              {diagnostics.warnings.map((warning) => (
                <span
                  key={warning}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-[#FEE2E2] text-[#B91C1C]"
                >
                  {warning}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
