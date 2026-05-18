/** TaskDetailPanel — 작업 상세 (execute 없음, token 원문 금지) */
import type { AssistantTask } from "@/types/assistant";
import { RiskBadge } from "@/components/ui/RiskBadge";

export function TaskDetailPanel({ task }: { task: AssistantTask }) {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-base font-semibold text-[#111827]">{task.title}</span>
        <RiskBadge level={task.risk.toLowerCase() as "low"|"medium"|"high"|"critical"} />
      </div>
      <dl className="text-sm space-y-1.5">
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">상태</dt>
          <dd className="font-mono text-xs text-[#374151]">{task.status}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">드라이런</dt>
          <dd>{task.dry_run
            ? <span className="text-[#1D4ED8] font-semibold text-xs">DRY_RUN 전용</span>
            : <span className="text-[#6B7280] text-xs">N/A</span>}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">제공자</dt>
          <dd className="font-mono text-xs">{task.provider}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">승인 토큰</dt>
          <dd className="text-xs">
            {task.approval_token_exists
              ? <span className="text-[#059669]">존재 (원문 표시 금지)</span>
              : <span className="text-[#9CA3AF]">없음</span>
            }
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">생성일시</dt>
          <dd className="text-xs font-mono">{task.created_at}</dd>
        </div>
      </dl>
      <div className="pt-2 border-t border-[#F3F4F6]">
        <p className="text-xs text-[#9CA3AF]">
          ℹ 실행 버튼 없음 — approve→execute 미연결 (B-1), DRY_RUN 해제 미승인 (B-2)
        </p>
      </div>
    </div>
  );
}
